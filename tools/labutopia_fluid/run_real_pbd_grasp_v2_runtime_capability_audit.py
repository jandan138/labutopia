#!/usr/bin/env python3
"""Run a read-only, no-go-only runtime capability audit for real PBD G0.

This runner intentionally does not construct a World, task, controller, or
robot. It may pump Kit only while the timeline remains stopped so PhysX can
complete a source-rigid-body cooked-collider property query. It never issues a
clearance certificate and therefore cannot produce G0_GO.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import secrets
import signal
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.controlled_contact import canonical_json_sha256  # noqa: E402
from utils.real_pbd_grasp_v2 import (  # noqa: E402
    build_stage_artifact,
    build_stage_evidence,
    evaluate_g0_runtime_capability_audit,
    serialize_stage_artifact,
    validate_g0_runtime_profile_extension_policy,
)


DEFAULT_ASSET = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_level1_pour_interndata_contact_grasp_rest_offset_zero_step600_layout_v1.usda"
)
SOURCE_ACTOR_PATH = "/World/beaker2"
SOURCE_SHELL_PATH = "/World/beaker2/mesh"
PARTICLE_PATH = "/World/InternDataParityFluid/Particles"
WRAPPER_PATH = "/World/beaker2/FluidSafeWrapperCanonical"
FORMAL_ISAAC41_PYTHON = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
)
FORMAL_ISAAC41_PREFIX = FORMAL_ISAAC41_PYTHON.parents[1]
FORMAL_PROPERTY_QUERY_EXPERIENCE = (
    FORMAL_ISAAC41_PREFIX
    / "lib/python3.10/site-packages/isaacsim/apps/"
    "omni.isaac.sim.python.gym.headless.kit"
)
EXPERIMENTAL_PROPERTY_QUERY_EXPERIENCE = (
    REPO_ROOT
    / "tools/labutopia_fluid/profiles/isaac41_g0_property_query_experimental.kit"
)
SNAPSHOT_BASENAME = "child_snapshot.json"
RUNTIME_RECEIPT_BASENAME = "child_runtime_receipt.json"
REPORT_BASENAME = "report.json"
ARTIFACT_BASENAME = "g0_stage_artifact.json"
CHILD_STDOUT_LOG_BASENAME = "child.stdout.log"
CHILD_STDERR_LOG_BASENAME = "child.stderr.log"
_CHILD_EXECUTION_STATUSES = frozenset({"COMPLETE", "CHILD_FAILURE", "CHILD_TIMEOUT"})
_STDERR_MARKER_NAMES = (
    "child_error_protocol",
    "kit_error",
    "kit_fatal",
    "native_abi_warning",
    "python_traceback",
)
_STDERR_DIAGNOSTIC_AUTHORITY = "real_pbd_g0_runtime_audit_stderr_diagnostic_v2"
_STDERR_SCANNER_POLICY = "ascii_line_severity_and_native_abi_v2"
_RUNTIME_ERROR_MARKER_NAMES = frozenset(
    {"child_error_protocol", "kit_error", "kit_fatal", "python_traceback"}
)


def _sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"real_pbd_g0_runtime_audit_{field}_invalid")
    if any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"real_pbd_g0_runtime_audit_{field}_invalid")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _approved_property_query_experience(experience_path: Path) -> Path:
    experience = experience_path.resolve()
    approved = {
        FORMAL_PROPERTY_QUERY_EXPERIENCE.resolve(),
        EXPERIMENTAL_PROPERTY_QUERY_EXPERIENCE.resolve(),
    }
    if experience not in approved:
        raise ValueError("real_pbd_g0_runtime_audit_experience_unapproved")
    if not experience.is_file():
        raise ValueError("real_pbd_g0_runtime_audit_experience_unavailable")
    return experience


def _profile_extension_policy(experience_path: Path) -> dict[str, Any]:
    experience = _approved_property_query_experience(experience_path)
    if experience == EXPERIMENTAL_PROPERTY_QUERY_EXPERIENCE.resolve():
        required_extensions = [
            {"name": "omni.kit.loop-isaac", "version": "1.2.0"},
            {"name": "omni.kit.usd.layers", "version": "2.1.31"},
            {"name": "omni.physx", "version": "106.0.20"},
            {"name": "omni.physx.stageupdate", "version": "106.0.20"},
            {"name": "omni.timeline", "version": "1.0.10"},
            {"name": "omni.usd", "version": "1.11.2"},
        ]
        forbidden_extension_names = ["omni.physx.fabric", "omni.physxfabric"]
    else:
        required_extensions = [{"name": "omni.physx", "version": "106.0.20"}]
        forbidden_extension_names = []
    return validate_g0_runtime_profile_extension_policy(
        {
            "authority": "real_pbd_g0_runtime_profile_extension_policy_v1",
            "schema_version": 1,
            "required_extensions": required_extensions,
            "forbidden_extension_names": forbidden_extension_names,
        }
    )


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("real_pbd_g0_runtime_audit_json_duplicate_key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"real_pbd_g0_runtime_audit_json_nonfinite_{value}")


def _read_canonical_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        stat_before = os.lstat(path)
    except OSError as exc:
        raise ValueError("real_pbd_g0_runtime_audit_child_snapshot_missing") from exc
    if not os.path.isfile(path) or os.path.islink(path) or stat_before.st_nlink != 1:
        raise ValueError("real_pbd_g0_runtime_audit_child_snapshot_invalid")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        os.close(descriptor)
    payload = b"".join(chunks)
    try:
        parsed = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_object_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("real_pbd_g0_runtime_audit_child_snapshot_invalid") from exc
    if not isinstance(parsed, Mapping) or payload != _canonical_json_bytes(dict(parsed)):
        raise ValueError("real_pbd_g0_runtime_audit_child_snapshot_noncanonical")
    stat_after = os.lstat(path)
    if (
        stat_before.st_ino != stat_after.st_ino
        or stat_before.st_size != stat_after.st_size
        or stat_before.st_mtime_ns != stat_after.st_mtime_ns
    ):
        raise ValueError("real_pbd_g0_runtime_audit_child_snapshot_changed")
    return dict(parsed), payload


def atomic_create_bytes(path: Path, payload: bytes) -> None:
    if path.exists():
        raise FileExistsError(f"real_pbd_g0_runtime_audit_output_exists:{path}")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise FileExistsError(f"real_pbd_g0_runtime_audit_output_exists:{path}") from exc
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_runtime_contract(value: Any) -> dict[str, str | int]:
    if not isinstance(value, Mapping):
        raise ValueError("real_pbd_g0_runtime_audit_runtime_contract_invalid")
    contract = copy.deepcopy(dict(value))
    expected = {
        "authority",
        "schema_version",
        "executable",
        "prefix",
        "python_version",
        "isaacsim_version",
        "numpy_version",
        "usd_version",
        "experience_path",
        "experience_sha256",
    }
    if (
        set(contract) != expected
        or contract.get("authority") != "real_pbd_g0_runtime_contract_v1"
        or contract.get("schema_version") != 1
    ):
        raise ValueError("real_pbd_g0_runtime_audit_runtime_contract_invalid")
    for field in (
        "executable",
        "prefix",
        "python_version",
        "isaacsim_version",
        "numpy_version",
        "usd_version",
        "experience_path",
        "experience_sha256",
    ):
        if not isinstance(contract[field], str) or not contract[field]:
            raise ValueError("real_pbd_g0_runtime_audit_runtime_contract_invalid")
    _sha256(contract["experience_sha256"], field="experience_sha256")
    if (
        not Path(contract["executable"]).is_absolute()
        or not Path(contract["prefix"]).is_absolute()
        or not Path(contract["experience_path"]).is_absolute()
    ):
        raise ValueError("real_pbd_g0_runtime_audit_runtime_contract_invalid")
    return contract


def formal_runtime_contract(
    *, experience_path: Path = FORMAL_PROPERTY_QUERY_EXPERIENCE
) -> dict[str, str | int]:
    experience = _approved_property_query_experience(experience_path)
    experience_sha256 = _sha256_file(experience)
    return _validate_runtime_contract(
        {
            "authority": "real_pbd_g0_runtime_contract_v1",
            "schema_version": 1,
            "executable": str(FORMAL_ISAAC41_PYTHON),
            "prefix": str(FORMAL_ISAAC41_PREFIX),
            "python_version": "3.10.20",
            "isaacsim_version": "4.1.0.0",
            "numpy_version": "1.26.4",
            "usd_version": "0.22.11",
            "experience_path": str(experience),
            "experience_sha256": experience_sha256,
        }
    )


def validate_audit_spec(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("real_pbd_g0_runtime_audit_spec_invalid")
    spec = copy.deepcopy(dict(value))
    expected = {
        "authority",
        "schema_version",
        "asset_path",
        "asset_sha256",
        "source_actor_path",
        "particle_path",
        "wrapper_path",
        "query_mode",
        "no_action_policy",
        "profile_extension_policy",
        "runtime_contract",
    }
    if (
        set(spec) != expected
        or spec.get("authority") != "real_pbd_g0_runtime_capability_audit_spec_v3"
        or spec.get("schema_version") != 3
        or spec.get("query_mode") != "QUERY_RIGID_BODY_WITH_COLLIDERS"
        or spec.get("no_action_policy") != "audited_read_only_no_world_v1"
    ):
        raise ValueError("real_pbd_g0_runtime_audit_spec_invalid")
    if not isinstance(spec["asset_path"], str) or not spec["asset_path"]:
        raise ValueError("real_pbd_g0_runtime_audit_spec_invalid")
    for field in ("asset_sha256",):
        _sha256(spec[field], field=field)
    for field in ("source_actor_path", "particle_path", "wrapper_path"):
        if not isinstance(spec[field], str) or not spec[field].startswith("/"):
            raise ValueError("real_pbd_g0_runtime_audit_spec_invalid")
    spec["runtime_contract"] = _validate_runtime_contract(spec["runtime_contract"])
    spec["profile_extension_policy"] = validate_g0_runtime_profile_extension_policy(
        spec["profile_extension_policy"]
    )
    return spec


def build_audit_spec(
    *,
    asset_path: Path,
    experience_path: Path = FORMAL_PROPERTY_QUERY_EXPERIENCE,
) -> dict[str, Any]:
    """Build a pure parent request; USD inspection belongs to the sealed child."""

    from tools.labutopia_fluid.run_real_pbd_grasp_v2_preflight import sha256_file

    asset = asset_path.resolve()
    spec = {
        "authority": "real_pbd_g0_runtime_capability_audit_spec_v3",
        "schema_version": 3,
        "asset_path": str(asset),
        "asset_sha256": sha256_file(asset),
        "source_actor_path": SOURCE_ACTOR_PATH,
        "particle_path": PARTICLE_PATH,
        "wrapper_path": WRAPPER_PATH,
        "query_mode": "QUERY_RIGID_BODY_WITH_COLLIDERS",
        "no_action_policy": "audited_read_only_no_world_v1",
        "profile_extension_policy": _profile_extension_policy(experience_path),
        "runtime_contract": formal_runtime_contract(experience_path=experience_path),
    }
    return validate_audit_spec(spec)


def _fallback_audit_spec(
    *,
    asset_path: Path,
    experience_path: Path = FORMAL_PROPERTY_QUERY_EXPERIENCE,
) -> dict[str, Any]:
    """Create a syntactically valid failure spec when static setup cannot read USD."""

    asset = asset_path.resolve()
    identity = canonical_json_sha256({"unavailable_asset_path": str(asset)})
    return validate_audit_spec(
        {
            "authority": "real_pbd_g0_runtime_capability_audit_spec_v3",
            "schema_version": 3,
            "asset_path": str(asset),
            "asset_sha256": identity,
            "source_actor_path": SOURCE_ACTOR_PATH,
            "particle_path": PARTICLE_PATH,
            "wrapper_path": WRAPPER_PATH,
            "query_mode": "QUERY_RIGID_BODY_WITH_COLLIDERS",
            "no_action_policy": "audited_read_only_no_world_v1",
            "profile_extension_policy": _profile_extension_policy(experience_path),
            "runtime_contract": formal_runtime_contract(experience_path=experience_path),
        }
    )


def runtime_python_executable() -> str:
    if not FORMAL_ISAAC41_PYTHON.is_file() or not os.access(FORMAL_ISAAC41_PYTHON, os.X_OK):
        raise RuntimeError("real_pbd_g0_runtime_audit_isaac_python_unavailable")
    return str(FORMAL_ISAAC41_PYTHON)


def _runtime_contract_matches(
    *, contract: Mapping[str, Any], observed: Mapping[str, Any]
) -> bool:
    required = (
        "executable",
        "prefix",
        "python_version",
        "isaacsim_version",
        "numpy_version",
        "usd_version",
        "experience_path",
        "experience_sha256",
    )
    if any(observed.get(field) != contract[field] for field in required):
        return False
    origins = observed.get("module_origins")
    if not isinstance(origins, Mapping) or set(origins) != {
        "isaacsim",
        "numpy",
        "pxr_usd",
        "omni_physx",
        "physx_bindings",
    }:
        return False
    prefix = str(contract["prefix"]).rstrip("/") + "/"
    return all(isinstance(origin, str) and origin.startswith(prefix) for origin in origins.values())


def _validate_runtime_receipt(
    *, receipt: Mapping[str, Any], spec: Mapping[str, Any], nonce: str
) -> tuple[dict[str, Any], bool]:
    if not isinstance(receipt, Mapping):
        raise ValueError("real_pbd_g0_runtime_audit_runtime_receipt_invalid")
    value = copy.deepcopy(dict(receipt))
    expected = {
        "authority",
        "schema_version",
        "parent_nonce_sha256",
        "audit_spec_sha256",
        "runtime_contract",
        "observed_runtime",
        "attestation_status",
    }
    if (
        set(value) != expected
        or value.get("authority") != "real_pbd_g0_runtime_capability_runtime_receipt_v1"
        or value.get("schema_version") != 1
        or value.get("parent_nonce_sha256") != nonce
        or value.get("audit_spec_sha256") != canonical_json_sha256(spec)
    ):
        raise ValueError("real_pbd_g0_runtime_audit_runtime_receipt_invalid")
    contract = _validate_runtime_contract(value["runtime_contract"])
    if contract != spec["runtime_contract"]:
        raise ValueError("real_pbd_g0_runtime_audit_runtime_receipt_contract_invalid")
    status = value.get("attestation_status")
    if status == "UNAVAILABLE":
        if value.get("observed_runtime") is not None:
            raise ValueError("real_pbd_g0_runtime_audit_runtime_receipt_invalid")
        return {**value, "runtime_contract": contract}, False
    observed = value.get("observed_runtime")
    if not isinstance(observed, Mapping) or set(observed) != {
        "executable",
        "prefix",
        "python_version",
        "isaacsim_version",
        "numpy_version",
        "usd_version",
        "experience_path",
        "experience_sha256",
        "module_origins",
    }:
        raise ValueError("real_pbd_g0_runtime_audit_runtime_receipt_invalid")
    if any(not isinstance(observed[field], str) or not observed[field] for field in observed if field != "module_origins"):
        raise ValueError("real_pbd_g0_runtime_audit_runtime_receipt_invalid")
    matches = _runtime_contract_matches(contract=contract, observed=observed)
    if status not in {"MATCH", "MISMATCH"} or (status == "MATCH") != matches:
        raise ValueError("real_pbd_g0_runtime_audit_runtime_receipt_invalid")
    return {**value, "runtime_contract": contract, "observed_runtime": dict(observed)}, matches


def _unavailable_runtime_receipt(*, spec: Mapping[str, Any], nonce: str) -> dict[str, Any]:
    return {
        "authority": "real_pbd_g0_runtime_capability_runtime_receipt_v1",
        "schema_version": 1,
        "parent_nonce_sha256": nonce,
        "audit_spec_sha256": canonical_json_sha256(spec),
        "runtime_contract": dict(spec["runtime_contract"]),
        "observed_runtime": None,
        "attestation_status": "UNAVAILABLE",
    }


def _runtime_receipt_from_child(
    *, spec: Mapping[str, Any], nonce: str, app: Any
) -> dict[str, Any]:
    import importlib.metadata

    import isaacsim
    import numpy
    import omni.physx
    from omni.physx.bindings import _physx
    from pxr import Usd

    experience_path = Path(app.config["experience"])
    observed = {
        # Preserve the invoked launcher path. Resolving it turns the approved
        # bin/python symlink into bin/python3.10 and loses contract identity.
        "executable": str(Path(sys.executable)),
        "prefix": str(Path(sys.prefix).resolve()),
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "isaacsim_version": importlib.metadata.version("isaacsim"),
        "numpy_version": numpy.__version__,
        "usd_version": ".".join(str(part) for part in Usd.GetVersion()),
        "experience_path": str(experience_path),
        "experience_sha256": _sha256_file(experience_path),
        "module_origins": {
            "isaacsim": str(Path(isaacsim.__file__).resolve()),
            "numpy": str(Path(numpy.__file__).resolve()),
            "pxr_usd": str(Path(Usd.__file__).resolve()),
            "omni_physx": str(Path(omni.physx.__file__).resolve()),
            "physx_bindings": str(Path(_physx.__file__).resolve()),
        },
    }
    status = "MATCH" if _runtime_contract_matches(
        contract=spec["runtime_contract"], observed=observed
    ) else "MISMATCH"
    return {
        "authority": "real_pbd_g0_runtime_capability_runtime_receipt_v1",
        "schema_version": 1,
        "parent_nonce_sha256": nonce,
        "audit_spec_sha256": canonical_json_sha256(spec),
        "runtime_contract": dict(spec["runtime_contract"]),
        "observed_runtime": observed,
        "attestation_status": status,
    }


def _child_stderr_diagnostic(stderr: bytes) -> dict[str, Any]:
    """Classify fixed runtime-severity markers without serializing log text."""

    if not isinstance(stderr, bytes):
        raise ValueError("real_pbd_g0_runtime_audit_child_stderr_invalid")
    marker_line_counts = dict.fromkeys(_STDERR_MARKER_NAMES, 0)
    for line in stderr.splitlines():
        if b"real_pbd_g0_runtime_audit_child_error:" in line:
            marker_line_counts["child_error_protocol"] += 1
        if line.startswith(b"[Error] ") or b" [Error] " in line:
            marker_line_counts["kit_error"] += 1
        if line.startswith(b"[Fatal] ") or b" [Fatal] " in line:
            marker_line_counts["kit_fatal"] += 1
        if (
            b"Possible version incompatibility. Attempting to load omni::" in line
            and b" against v" in line
        ):
            marker_line_counts["native_abi_warning"] += 1
        if b"Traceback (most recent call last):" in line:
            marker_line_counts["python_traceback"] += 1
    runtime_log_clean = not any(marker_line_counts.values())
    return {
        "authority": _STDERR_DIAGNOSTIC_AUTHORITY,
        "schema_version": 2,
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stderr_byte_count": len(stderr),
        "scanner_policy": _STDERR_SCANNER_POLICY,
        "marker_line_counts": marker_line_counts,
        "runtime_log_clean": runtime_log_clean,
    }


def _child_execution_record(
    *, status: str, returncode: int | None, stderr: bytes
) -> dict[str, Any]:
    if status not in _CHILD_EXECUTION_STATUSES:
        raise ValueError("real_pbd_g0_runtime_audit_child_execution_status_invalid")
    if returncode is not None and (
        isinstance(returncode, bool) or not isinstance(returncode, int)
    ):
        raise ValueError("real_pbd_g0_runtime_audit_child_execution_returncode_invalid")
    if status == "COMPLETE" and returncode != 0:
        raise ValueError("real_pbd_g0_runtime_audit_child_execution_status_invalid")
    return {
        "authority": "real_pbd_g0_runtime_audit_child_execution_v1",
        "schema_version": 1,
        "parent_status": status,
        "returncode": returncode,
        "stderr_diagnostic": _child_stderr_diagnostic(stderr),
    }


def finalize_child_snapshot(
    *,
    snapshot: Mapping[str, Any],
    audit_spec: Mapping[str, Any],
    parent_nonce_sha256: str,
    child_stdout: bytes,
    child_stderr: bytes,
    child_execution_status: str,
    child_returncode: int | None,
    runtime_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute one child snapshot into a parent-owned, no-go-only report."""

    spec = validate_audit_spec(audit_spec)
    nonce = _sha256(parent_nonce_sha256, field="parent_nonce_sha256")
    if not isinstance(child_stdout, bytes):
        raise ValueError("real_pbd_g0_runtime_audit_child_stdout_invalid")
    execution = _child_execution_record(
        status=child_execution_status,
        returncode=child_returncode,
        stderr=child_stderr,
    )
    stdout_sha = hashlib.sha256(child_stdout).hexdigest()
    stderr_sha = execution["stderr_diagnostic"]["stderr_sha256"]
    normalized_receipt, runtime_contract_matches = _validate_runtime_receipt(
        receipt=runtime_receipt,
        spec=spec,
        nonce=nonce,
    )
    runtime_receipt_sha = hashlib.sha256(
        _canonical_json_bytes(normalized_receipt)
    ).hexdigest()
    if not isinstance(snapshot, Mapping):
        raise ValueError("real_pbd_g0_runtime_audit_snapshot_invalid")
    raw = copy.deepcopy(dict(snapshot))
    if raw.get("parent_nonce_sha256") != nonce:
        raise ValueError("real_pbd_g0_runtime_audit_nonce_invalid")
    if (
        raw.get("audit_spec_sha256") != canonical_json_sha256(spec)
        or raw.get("source_actor_path") != spec["source_actor_path"]
    ):
        raise ValueError("real_pbd_g0_runtime_audit_spec_binding_invalid")
    profile_extension_evidence = raw.get("profile_extension_evidence")
    if (
        not isinstance(profile_extension_evidence, Mapping)
        or profile_extension_evidence.get("policy")
        != spec["profile_extension_policy"]
    ):
        raise ValueError("real_pbd_g0_runtime_audit_spec_binding_invalid")
    if raw.get("audit_status") == "COMPLETE" and (
        raw.get("asset_sha256") != spec["asset_sha256"]
        or raw.get("fixture_identity_sha256")
        != raw.get("input_closure_before_sha256")
        or raw.get("fixture_identity_sha256")
        != raw.get("input_closure_after_sha256")
    ):
        raise ValueError("real_pbd_g0_runtime_audit_spec_binding_invalid")
    report = evaluate_g0_runtime_capability_audit(snapshot=raw)
    lifecycle_clean = bool(
        execution["parent_status"] == "COMPLETE" and execution["returncode"] == 0
    )
    runtime_log_clean = execution["stderr_diagnostic"]["runtime_log_clean"]
    marker_line_counts = execution["stderr_diagnostic"]["marker_line_counts"]
    reasons = list(report["no_go_reasons"])
    if not lifecycle_clean:
        reasons.append("child_lifecycle_not_clean")
    if any(marker_line_counts[name] for name in _RUNTIME_ERROR_MARKER_NAMES):
        reasons.append("child_runtime_errors_observed")
    if marker_line_counts["native_abi_warning"]:
        reasons.append("native_abi_version_incompatibility_warning_observed")
    if not runtime_contract_matches:
        reasons.append("runtime_contract_mismatch")
    payload = {
        **{
            key: value
            for key, value in report.items()
            if key not in {"sha256", "checks", "no_go_reasons"}
        },
        "checks": {
            **report["checks"],
            "child_lifecycle_clean": lifecycle_clean,
            "runtime_log_clean": runtime_log_clean,
            "runtime_contract_matches": runtime_contract_matches,
        },
        "child_stdout_sha256": stdout_sha,
        "child_stderr_sha256": stderr_sha,
        "child_execution": execution,
        "runtime_receipt": normalized_receipt,
        "child_runtime_receipt_sha256": runtime_receipt_sha,
        "no_go_reasons": sorted(set(reasons)),
        "parent_recomputed": True,
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


def _stage_snapshot_hash(stage: Any, root_path: str) -> str:
    from pxr import Usd

    root = stage.GetPrimAtPath(root_path)
    records = []
    if not root or not root.IsValid():
        raise RuntimeError(f"real_pbd_g0_runtime_audit_required_prim_missing:{root_path}")
    for prim in Usd.PrimRange(root):
        attributes = {}
        for attribute in prim.GetAttributes():
            if attribute.HasAuthoredValueOpinion():
                samples = [float(sample) for sample in attribute.GetTimeSamples()]
                attributes[str(attribute.GetName())] = {
                    "default": str(attribute.Get()),
                    "time_samples": {
                        str(sample): str(attribute.Get(sample)) for sample in samples
                    },
                    "metadata": {
                        str(key): str(value)
                        for key, value in attribute.GetAllMetadata().items()
                    },
                    "connections": sorted(
                        str(connection) for connection in attribute.GetConnections()
                    ),
                }
        relationships = {
            str(relationship.GetName()): sorted(
                str(target) for target in relationship.GetTargets()
            )
            for relationship in prim.GetRelationships()
        }
        metadata = {
            str(key): str(value)
            for key, value in prim.GetAllMetadata().items()
        }
        records.append(
            {
                "path": str(prim.GetPath()),
                "type": str(prim.GetTypeName()),
                "schemas": sorted(str(item) for item in prim.GetAppliedSchemas()),
                "metadata": metadata,
                "attributes": attributes,
                "relationships": relationships,
            }
        )
    return canonical_json_sha256({"root_path": root_path, "records": records})


def _require_pristine_stage(stage: Any) -> None:
    children = list(stage.GetPseudoRoot().GetChildren())
    session_prims = list(stage.GetSessionLayer().rootPrims)
    if children or session_prims:
        raise RuntimeError(
            "real_pbd_g0_runtime_audit_stage_not_pristine:"
            f"children={[str(prim.GetPath()) for prim in children]}:"
            f"session={[str(prim.path) for prim in session_prims]}"
        )


def _timeline_receipt(timeline: Any) -> dict[str, Any]:
    return {
        "is_playing": bool(timeline.is_playing()),
        "time_s": float(timeline.get_current_time()),
    }


def _query_source_cooked_colliders(
    app: Any,
    stage: Any,
    source_path: str,
    timeline: Any,
    profile_extension_policy: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    from omni.physx import get_physx_property_query_interface
    from omni.physx.bindings._physx import PhysxPropertyQueryMode, PhysxPropertyQueryResult
    from pxr import PhysicsSchemaTools, UsdUtils

    source = stage.GetPrimAtPath(source_path)
    if not source or not source.IsValid():
        raise RuntimeError("real_pbd_g0_runtime_audit_source_missing")
    result: dict[str, Any] = {
        "status": "FAILED",
        "query_mode": "QUERY_RIGID_BODY_WITH_COLLIDERS",
        "rigid_body_owner_path": source_path,
        "finished_callback_count": 0,
        "callback_errors": [],
        "colliders": [],
        "mass_kg": None,
        "center_of_mass_local_m": None,
        "diagonal_inertia_kg_m2": None,
    }
    finished = {"value": False}

    def rigid_body_callback(info: Any) -> None:
        if info.result != PhysxPropertyQueryResult.VALID:
            result["callback_errors"].append(f"rigid_body:{info.result}")
            return
        result["mass_kg"] = float(info.mass)
        result["center_of_mass_local_m"] = list(info.center_of_mass)
        result["diagonal_inertia_kg_m2"] = list(info.inertia)

    def collider_callback(info: Any) -> None:
        if info.result != PhysxPropertyQueryResult.VALID:
            result["callback_errors"].append(f"collider:{info.result}")
            return
        result["colliders"].append(
            {
                "path": str(PhysicsSchemaTools.intToSdfPath(info.path_id)),
                "aabb_local_min_m": list(info.aabb_local_min),
                "aabb_local_max_m": list(info.aabb_local_max),
                "volume_m3": float(info.volume),
            }
        )

    def finished_callback() -> None:
        result["finished_callback_count"] += 1
        finished["value"] = True

    before = _timeline_receipt(timeline)
    if before["is_playing"] or before["time_s"] != 0.0:
        raise RuntimeError("real_pbd_g0_runtime_audit_timeline_not_pristine")
    extension_before = _runtime_extension_closure(app)
    update_closure_hashes = []
    get_physx_property_query_interface().query_prim(
        stage_id=UsdUtils.StageCache.Get().Insert(stage).ToLongInt(),
        prim_id=PhysicsSchemaTools.sdfPathToInt(source.GetPath()),
        query_mode=PhysxPropertyQueryMode.QUERY_RIGID_BODY_WITH_COLLIDERS,
        rigid_body_fn=rigid_body_callback,
        collider_fn=collider_callback,
        finished_fn=finished_callback,
        timeout_ms=60_000,
    )
    deadline = time.monotonic() + 60.0
    while time.monotonic() < deadline:
        if finished["value"]:
            break
        if _timeline_receipt(timeline) != before:
            raise RuntimeError("real_pbd_g0_runtime_audit_timeline_changed_before_pump")
        app.update()
        update_closure_hashes.append(_runtime_extension_closure(app)["closure_sha256"])
        if _timeline_receipt(timeline) != before:
            raise RuntimeError("real_pbd_g0_runtime_audit_timeline_changed_during_pump")
    if not finished["value"]:
        result["status"] = "TIMEOUT"
    elif result["callback_errors"]:
        result["status"] = "FAILED"
    else:
        result["status"] = "COMPLETE"
    result["colliders"].sort(key=lambda item: item["path"])
    after = _timeline_receipt(timeline)
    if after != before:
        raise RuntimeError("real_pbd_g0_runtime_audit_timeline_changed_after_query")
    extension_after = _runtime_extension_closure(app)
    policy = validate_g0_runtime_profile_extension_policy(profile_extension_policy)
    extension_evidence = {
        "authority": "real_pbd_g0_runtime_profile_extension_evidence_v1",
        "schema_version": 1,
        "policy": policy,
        "policy_sha256": canonical_json_sha256(policy),
        "before_query": extension_before,
        "after_query": extension_after,
        "query_update_closure_sha256es": update_closure_hashes,
    }
    return result, before, after, extension_evidence


def _runtime_enabled_source_colliders(stage: Any, *, source_path: str) -> list[str]:
    from pxr import Usd, UsdPhysics

    source = stage.GetPrimAtPath(source_path)
    if not source or not source.IsValid():
        raise RuntimeError("real_pbd_g0_runtime_audit_source_missing")
    paths = []
    for prim in Usd.PrimRange(source):
        if not prim.HasAPI(UsdPhysics.CollisionAPI):
            continue
        enabled = prim.GetAttribute("physics:collisionEnabled")
        if enabled and enabled.Get() is False:
            continue
        paths.append(str(prim.GetPath()))
    return sorted(paths)


def _authored_offsets(stage: Any, paths: Sequence[str]) -> list[dict[str, Any]]:
    from pxr import PhysxSchema

    records = []
    for path in paths:
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            raise RuntimeError("real_pbd_g0_runtime_audit_collider_missing")
        api = PhysxSchema.PhysxCollisionAPI(prim)
        contact = api.GetContactOffsetAttr()
        rest = api.GetRestOffsetAttr()
        contact_authored = bool(contact and contact.HasAuthoredValueOpinion())
        rest_authored = bool(rest and rest.HasAuthoredValueOpinion())
        records.append(
            {
                "path": path,
                "contact_offset_m": float(contact.Get()) if contact_authored else None,
                "rest_offset_m": float(rest.Get()) if rest_authored else None,
                "contact_offset_authored": contact_authored,
                "rest_offset_authored": rest_authored,
            }
        )
    return records


def _stable_file_sha256(path: Path) -> str:
    try:
        before = os.lstat(path)
    except OSError as exc:
        raise RuntimeError("real_pbd_g0_runtime_audit_extension_manifest_missing") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RuntimeError("real_pbd_g0_runtime_audit_extension_manifest_invalid")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise RuntimeError("real_pbd_g0_runtime_audit_extension_manifest_invalid")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    finally:
        os.close(descriptor)
    after = os.lstat(path)
    if (
        before.st_dev != opened.st_dev
        or before.st_ino != opened.st_ino
        or before.st_size != opened.st_size
        or before.st_mtime_ns != opened.st_mtime_ns
        or before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise RuntimeError("real_pbd_g0_runtime_audit_extension_manifest_changed")
    return digest.hexdigest()


def _runtime_extension_closure(app: Any) -> dict[str, Any]:
    manager = app.app.get_extension_manager()
    approved_roots = (
        FORMAL_ISAAC41_PREFIX.resolve(),
        EXPERIMENTAL_PROPERTY_QUERY_EXPERIENCE.parent.resolve(),
    )
    records = []
    for index, extension in enumerate(manager.get_extensions()):
        if not extension["enabled"]:
            continue
        fields = {
            "name": extension["name"],
            "id": extension["id"],
            "path": extension["path"],
        }
        for field, value in fields.items():
            if not isinstance(value, str) or not value:
                raise RuntimeError(
                    "real_pbd_g0_runtime_audit_extension_record_invalid:"
                    f"{index}:{field}:{type(value).__name__}"
                )
        name = fields["name"]
        extension_id = fields["id"]
        raw_path = fields["path"]
        metadata = manager.get_extension_dict(extension_id)
        metadata_get = getattr(metadata, "get", None)
        if not callable(metadata_get):
            raise RuntimeError(
                "real_pbd_g0_runtime_audit_extension_record_invalid:"
                f"{index}:metadata:{type(metadata).__name__}"
            )
        package = metadata_get("package", None)
        package_get = getattr(package, "get", None)
        version = package_get("version", None) if callable(package_get) else None
        if not isinstance(version, str) or not version:
            raise RuntimeError(
                "real_pbd_g0_runtime_audit_extension_record_invalid:"
                f"{index}:metadata_version:{type(version).__name__}"
            )
        path = Path(raw_path).resolve()
        if not any(path.is_relative_to(root) for root in approved_roots):
            raise RuntimeError("real_pbd_g0_runtime_audit_extension_path_unapproved")
        raw_manifest_path = metadata_get("configPath", None)
        if not isinstance(raw_manifest_path, str) or not raw_manifest_path:
            raw_manifest_path = str(path / "config/extension.toml")
        manifest_path = Path(raw_manifest_path).resolve()
        if not any(manifest_path.is_relative_to(root) for root in approved_roots):
            raise RuntimeError("real_pbd_g0_runtime_audit_extension_manifest_unapproved")
        records.append(
            {
                "name": name,
                "id": extension_id,
                "version": version,
                "path": str(path),
                "manifest_path": str(manifest_path),
                "manifest_sha256": _stable_file_sha256(manifest_path),
            }
        )
    records.sort(key=lambda record: record["id"])
    if (
        len({record["id"] for record in records}) != len(records)
        or len({record["name"] for record in records}) != len(records)
    ):
        raise RuntimeError("real_pbd_g0_runtime_audit_extension_closure_ambiguous")
    return {
        "authority": "real_pbd_g0_runtime_extension_closure_v1",
        "schema_version": 1,
        "capture_status": "COMPLETE",
        "records": records,
        "closure_sha256": canonical_json_sha256({"records": records}),
    }


def _not_attempted_profile_extension_evidence(policy: Mapping[str, Any]) -> dict[str, Any]:
    normalized_policy = validate_g0_runtime_profile_extension_policy(policy)
    unavailable = {
        "authority": "real_pbd_g0_runtime_extension_closure_v1",
        "schema_version": 1,
        "capture_status": "NOT_ATTEMPTED",
        "records": None,
        "closure_sha256": None,
    }
    return {
        "authority": "real_pbd_g0_runtime_profile_extension_evidence_v1",
        "schema_version": 1,
        "policy": normalized_policy,
        "policy_sha256": canonical_json_sha256(normalized_policy),
        "before_query": unavailable,
        "after_query": copy.deepcopy(unavailable),
        "query_update_closure_sha256es": [],
    }


def _write_child_snapshot(path: Path, snapshot: Mapping[str, Any]) -> None:
    atomic_create_bytes(path, _canonical_json_bytes(dict(snapshot)))


def _run_child(
    *,
    spec_path: Path,
    nonce: str,
    snapshot_path: Path,
    runtime_receipt_path: Path,
    headless: bool,
) -> int:
    app = None
    try:
        from isaacsim import SimulationApp

        spec, _ = _read_canonical_json(spec_path)
        spec = validate_audit_spec(spec)
        app = SimulationApp(
            {"headless": bool(headless), "width": 64, "height": 64},
            experience=spec["runtime_contract"]["experience_path"],
        )
        receipt = _runtime_receipt_from_child(spec=spec, nonce=nonce, app=app)
        _write_child_snapshot(runtime_receipt_path, receipt)
        if receipt["attestation_status"] != "MATCH":
            print("real_pbd_g0_runtime_audit_child_error:RuntimeError:runtime_contract_mismatch", file=sys.stderr)
            return 2

        import omni.timeline
        import omni.usd
        from tools.labutopia_fluid.run_real_pbd_grasp_v2_preflight import (
            read_static_fixture,
            sha256_file,
            usd_dependency_closure,
        )

        asset = Path(spec["asset_path"])
        asset_sha256_before = sha256_file(asset)
        closure_before = usd_dependency_closure(asset)["usd_dependency_closure_sha256"]
        fixture = read_static_fixture(asset)
        expected_paths = sorted([SOURCE_SHELL_PATH, *fixture["wrapper_collider_paths"]])
        if asset_sha256_before != spec["asset_sha256"]:
            raise RuntimeError("real_pbd_g0_runtime_audit_input_identity_changed_before_query")

        timeline = omni.timeline.get_timeline_interface()
        if timeline.is_playing():
            raise RuntimeError("real_pbd_g0_runtime_audit_timeline_already_playing")
        usd_context = omni.usd.get_context()
        usd_context.new_stage()
        stage = usd_context.get_stage()
        stage.GetRootLayer().Clear()
        stage.GetSessionLayer().Clear()
        _require_pristine_stage(stage)
        world_root = stage.DefinePrim("/World", "Xform")
        world_root.GetReferences().AddReference(spec["asset_path"])
        baseline_timeline = _timeline_receipt(timeline)
        for _ in range(8):
            if _timeline_receipt(timeline) != baseline_timeline:
                raise RuntimeError("real_pbd_g0_runtime_audit_timeline_changed_while_loading")
            app.update()
            if _timeline_receipt(timeline) != baseline_timeline:
                raise RuntimeError("real_pbd_g0_runtime_audit_timeline_changed_while_loading")
        runtime_paths = _runtime_enabled_source_colliders(
            stage, source_path=spec["source_actor_path"]
        )
        if runtime_paths != expected_paths:
            raise RuntimeError("real_pbd_g0_runtime_audit_source_collider_inventory_changed")
        source_before = _stage_snapshot_hash(stage, spec["source_actor_path"])
        particle_before = _stage_snapshot_hash(stage, spec["particle_path"])
        root_before = _stage_snapshot_hash(stage, "/World")
        session_before = canonical_json_sha256(
            {"session_layer": stage.GetSessionLayer().ExportToString()}
        )
        (
            query,
            query_timeline_before,
            query_timeline_after,
            profile_extension_evidence,
        ) = _query_source_cooked_colliders(
            app,
            stage,
            spec["source_actor_path"],
            timeline,
            spec["profile_extension_policy"],
        )
        closure_after = usd_dependency_closure(asset)["usd_dependency_closure_sha256"]
        asset_sha256_after = sha256_file(asset)
        if (
            closure_after != closure_before
            or asset_sha256_after != asset_sha256_before
            or asset_sha256_after != spec["asset_sha256"]
        ):
            raise RuntimeError("real_pbd_g0_runtime_audit_input_identity_changed_after_query")
        source_after = _stage_snapshot_hash(stage, spec["source_actor_path"])
        particle_after = _stage_snapshot_hash(stage, spec["particle_path"])
        root_after = _stage_snapshot_hash(stage, "/World")
        session_after = canonical_json_sha256(
            {"session_layer": stage.GetSessionLayer().ExportToString()}
        )
        particle_count = 0
        particle_width_m = None
        particle_prim = stage.GetPrimAtPath(PARTICLE_PATH)
        if particle_prim and particle_prim.IsValid():
            attr = particle_prim.GetAttribute("physxParticle:simulationPoints")
            if attr:
                values = attr.Get()
                if values is not None:
                    particle_count = len(values)
            width_attr = particle_prim.GetAttribute("widths")
            if width_attr:
                widths = width_attr.Get()
                if widths is not None and len(widths) > 0:
                    particle_width_m = float(widths[0])
        expected_particle_count = 3600
        particle_ids_available = particle_count == expected_particle_count

        water_density_kg_m3 = 1000.0
        particle_mass_kg = 0.0
        effective_filled_mass_kg = 0.0
        if particle_width_m is not None and particle_width_m > 0:
            particle_radius_m = particle_width_m / 2.0
            particle_volume_m3 = (4.0 / 3.0) * math.pi * (particle_radius_m ** 3)
            particle_mass_kg = particle_volume_m3 * water_density_kg_m3
            effective_filled_mass_kg = particle_mass_kg * particle_count
        filled_load_available = (
            particle_ids_available
            and particle_width_m is not None
            and particle_width_m > 0
        )

        snapshot = {
            "authority": "real_pbd_g0_runtime_capability_snapshot_v2",
            "schema_version": 2,
            "run_id": secrets.token_hex(16),
            "parent_nonce_sha256": nonce,
            "audit_spec_sha256": canonical_json_sha256(spec),
            "asset_sha256": asset_sha256_after,
            "fixture_identity_sha256": closure_before,
            "source_actor_path": spec["source_actor_path"],
            "audit_status": "COMPLETE",
            "input_closure_before_sha256": closure_before,
            "input_closure_after_sha256": closure_after,
            "source_stage_before_sha256": source_before,
            "source_stage_after_sha256": source_after,
            "particle_stage_before_sha256": particle_before,
            "particle_stage_after_sha256": particle_after,
            "session_layer_before_sha256": session_before,
            "session_layer_after_sha256": session_after,
            "root_stage_before_sha256": root_before,
            "root_stage_after_sha256": root_after,
            "timeline_checkpoints": {
                "before_query": query_timeline_before,
                "after_query": query_timeline_after,
            },
            "no_motion_checks": {
                "world_constructed": False,
                "task_constructed": False,
                "controller_constructed": False,
                "robot_constructed": False,
                "world_reset_called": False,
                "world_step_called": False,
                "action_applied": False,
                "source_write_detected": source_before != source_after,
                "particle_write_detected": particle_before != particle_after,
            },
            "expected_source_collider_paths": expected_paths,
            "cooked_source_query": query,
            "authored_offsets": _authored_offsets(stage, expected_paths),
            "profile_extension_evidence": profile_extension_evidence,
            "particle_authority": {
                "authority": "stable_runtime_particle_ids_v1",
                "expected_count": particle_count,
                "stable_ids_sha256": (
                    canonical_json_sha256(
                        {"ids": list(range(particle_count))}
                    )
                    if particle_ids_available
                    else None
                ),
                "particle_id_manifest_sha256": (
                    canonical_json_sha256(
                        {"method": "authored_array_index_v1", "count": particle_count}
                    )
                    if particle_ids_available
                    else None
                ),
                "particle_ids_available": particle_ids_available,
                "filled_load_available": filled_load_available,
                "particle_width_m": particle_width_m,
                "water_density_kg_m3": water_density_kg_m3,
                "particle_mass_kg": particle_mass_kg,
                "effective_filled_mass_kg": effective_filled_mass_kg,
            },
            "capability_status": {
                "robot_table_cooked_geometry": "UNAVAILABLE",
                "physx_effective_offsets": "UNAVAILABLE",
                "signed_swept_clearance": "UNAVAILABLE",
                "stable_particle_ids": (
                    "AVAILABLE" if particle_ids_available else "UNAVAILABLE"
                ),
                "filled_load_authority": (
                    "AVAILABLE" if filled_load_available else "UNAVAILABLE"
                ),
            },
        }
        _write_child_snapshot(snapshot_path, snapshot)
        return 0
    except BaseException as exc:
        print(f"real_pbd_g0_runtime_audit_child_error:{type(exc).__name__}:{exc}", file=sys.stderr)
        return 2
    finally:
        if app is not None:
            app.close()


def _failure_snapshot(*, spec: Mapping[str, Any], nonce: str, status: str) -> dict[str, Any]:
    paths = [SOURCE_SHELL_PATH]
    return {
        "authority": "real_pbd_g0_runtime_capability_snapshot_v2",
        "schema_version": 2,
        "run_id": "parent-generated-no-go",
        "parent_nonce_sha256": nonce,
        "audit_spec_sha256": canonical_json_sha256(spec),
        "asset_sha256": spec["asset_sha256"],
        "fixture_identity_sha256": spec["asset_sha256"],
        "source_actor_path": spec["source_actor_path"],
        "audit_status": status,
        "input_closure_before_sha256": spec["asset_sha256"],
        "input_closure_after_sha256": "1" * 64,
        "source_stage_before_sha256": "0" * 64,
        "source_stage_after_sha256": "1" * 64,
        "particle_stage_before_sha256": "0" * 64,
        "particle_stage_after_sha256": "1" * 64,
        "session_layer_before_sha256": "0" * 64,
        "session_layer_after_sha256": "1" * 64,
        "root_stage_before_sha256": "0" * 64,
        "root_stage_after_sha256": "1" * 64,
        "timeline_checkpoints": {
            "before_query": {"is_playing": False, "time_s": 0.0},
            "after_query": {"is_playing": True, "time_s": 1.0},
        },
        "no_motion_checks": {
            "world_constructed": False,
            "task_constructed": False,
            "controller_constructed": False,
            "robot_constructed": False,
            "world_reset_called": False,
            "world_step_called": False,
            "action_applied": False,
            "source_write_detected": True,
            "particle_write_detected": True,
        },
        "expected_source_collider_paths": paths,
        "cooked_source_query": {
            "status": "FAILED",
            "query_mode": spec["query_mode"],
            "rigid_body_owner_path": spec["source_actor_path"],
            "finished_callback_count": 0,
            "callback_errors": [status.lower()],
            "colliders": [],
            "mass_kg": None,
            "center_of_mass_local_m": None,
            "diagonal_inertia_kg_m2": None,
        },
        "authored_offsets": [],
        "profile_extension_evidence": _not_attempted_profile_extension_evidence(
            spec["profile_extension_policy"]
        ),
        "particle_authority": {
            "authority": "stable_runtime_particle_ids_v1",
            "expected_count": 0,
            "stable_ids_sha256": None,
            "particle_id_manifest_sha256": None,
            "particle_ids_available": False,
        },
        "capability_status": {
            "robot_table_cooked_geometry": "UNAVAILABLE",
            "physx_effective_offsets": "UNAVAILABLE",
            "signed_swept_clearance": "UNAVAILABLE",
            "stable_particle_ids": "UNAVAILABLE",
            "filled_load_authority": "UNAVAILABLE",
        },
    }


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=10)


def _sealed_child_environment(temporary: Path) -> dict[str, str]:
    home = temporary / "home"
    tmpdir = temporary / "tmp"
    xdg_cache = temporary / "xdg-cache"
    xdg_config = temporary / "xdg-config"
    xdg_data = temporary / "xdg-data"
    xdg_state = temporary / "xdg-state"
    for directory in (home, tmpdir, xdg_cache, xdg_config, xdg_data, xdg_state):
        directory.mkdir()
    target_site = FORMAL_ISAAC41_PREFIX / "lib/python3.10/site-packages"
    target_libraries = [
        target_site / "isaacsim/extscache/omni.cuda.libs/bin",
        target_site / "isaacsim/extscache/omni.gpu_foundation/bin/deps",
        target_site / "torch/lib",
    ]
    environment = {
        "HOME": str(home),
        "TMPDIR": str(tmpdir),
        "XDG_CACHE_HOME": str(xdg_cache),
        "XDG_CONFIG_HOME": str(xdg_config),
        "XDG_DATA_HOME": str(xdg_data),
        "XDG_STATE_HOME": str(xdg_state),
        "PATH": f"{FORMAL_ISAAC41_PREFIX / 'bin'}:/usr/local/bin:/usr/bin:/bin",
        "LD_LIBRARY_PATH": ":".join(
            str(path) for path in target_libraries if path.is_dir()
        ),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "ACCEPT_EULA": "Y",
        "OMNI_KIT_ACCEPT_EULA": "YES",
    }
    for name in (
        "NVIDIA_VISIBLE_DEVICES",
        "CUDA_VISIBLE_DEVICES",
        "NVIDIA_DRIVER_CAPABILITIES",
        "VK_DRIVER_FILES",
    ):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    return environment


def _child_command(
    *, spec_path: Path, nonce_sha256: str, snapshot_path: Path, runtime_receipt_path: Path
) -> list[str]:
    runner = str(Path(__file__).resolve())
    bootstrap = (
        "import runpy,sys;"
        f"sys.path.insert(0,{str(REPO_ROOT)!r});"
        f"sys.argv=[{runner!r},*sys.argv[1:]];"
        f"runpy.run_path({runner!r},run_name='__main__')"
    )
    return [
        runtime_python_executable(),
        "-I",
        "-B",
        "-c",
        bootstrap,
        "--child",
        "--spec",
        str(spec_path),
        "--nonce-sha256",
        nonce_sha256,
        "--snapshot-out",
        str(snapshot_path),
        "--runtime-receipt-out",
        str(runtime_receipt_path),
    ]


def run_parent(
    *,
    asset_path: Path,
    out_dir: Path,
    timeout_s: float,
    experience_path: Path = FORMAL_PROPERTY_QUERY_EXPERIENCE,
) -> int:
    out_dir.mkdir(parents=True, exist_ok=False)
    if not isinstance(timeout_s, (int, float)) or not math.isfinite(float(timeout_s)) or float(timeout_s) <= 0.0:
        timeout_s = 1.0
        timeout_invalid = True
    else:
        timeout_s = float(timeout_s)
        timeout_invalid = False
    try:
        spec = build_audit_spec(
            asset_path=asset_path, experience_path=experience_path
        )
        setup_status = "COMPLETE"
    except BaseException:
        spec = _fallback_audit_spec(
            asset_path=asset_path, experience_path=experience_path
        )
        setup_status = "CHILD_FAILURE"
    if timeout_invalid:
        setup_status = "CHILD_FAILURE"
    nonce = secrets.token_hex(32)
    nonce_sha = hashlib.sha256(nonce.encode("ascii")).hexdigest()
    with tempfile.TemporaryDirectory(prefix="real_pbd_g0_audit_") as temporary_root:
        temporary = Path(temporary_root)
        spec_path = temporary / "audit_spec.json"
        snapshot_path = temporary / SNAPSHOT_BASENAME
        runtime_receipt_path = temporary / RUNTIME_RECEIPT_BASENAME
        atomic_create_bytes(spec_path, _canonical_json_bytes(spec))
        environment = _sealed_child_environment(temporary)
        if setup_status != "COMPLETE":
            stdout = b""
            stderr = b"real_pbd_g0_runtime_audit_setup_failure\n"
            status = setup_status
            process = None
        else:
            try:
                process = subprocess.Popen(
                    _child_command(
                        spec_path=spec_path,
                        nonce_sha256=nonce_sha,
                        snapshot_path=snapshot_path,
                        runtime_receipt_path=runtime_receipt_path,
                    ),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                    env=environment,
                )
                status = "COMPLETE"
                try:
                    stdout, stderr = process.communicate(timeout=timeout_s)
                except subprocess.TimeoutExpired:
                    status = "CHILD_TIMEOUT"
                    _terminate_process_group(process)
                    stdout, stderr = process.communicate()
                if status == "COMPLETE":
                    try:
                        os.killpg(process.pid, 0)
                    except ProcessLookupError:
                        pass
                    else:
                        status = "CHILD_FAILURE"
                        _terminate_process_group(process)
            except BaseException as exc:
                process = None
                status = "CHILD_FAILURE"
                stdout = b""
                stderr = f"real_pbd_g0_runtime_audit_launcher_failure:{type(exc).__name__}:{exc}\n".encode(
                    "utf-8"
                )
        child_returncode = process.returncode if process is not None else None
        if status == "COMPLETE" and child_returncode != 0:
            status = "CHILD_FAILURE"
        atomic_create_bytes(out_dir / CHILD_STDOUT_LOG_BASENAME, stdout)
        atomic_create_bytes(out_dir / CHILD_STDERR_LOG_BASENAME, stderr)
        snapshot: dict[str, Any] | None = None
        snapshot_bytes: bytes | None = None
        runtime_receipt = _unavailable_runtime_receipt(spec=spec, nonce=nonce_sha)
        if process is not None:
            try:
                if (
                    build_audit_spec(
                        asset_path=asset_path, experience_path=experience_path
                    )
                    != spec
                ):
                    raise ValueError("real_pbd_g0_runtime_audit_input_request_changed")
            except BaseException:
                status = "CHILD_FAILURE"
            try:
                snapshot, snapshot_bytes = _read_canonical_json(snapshot_path)
            except BaseException:
                snapshot = None
                snapshot_bytes = None
                status = "CHILD_FAILURE"
            try:
                runtime_receipt, runtime_receipt_bytes = _read_canonical_json(
                    runtime_receipt_path
                )
                _validate_runtime_receipt(
                    receipt=runtime_receipt,
                    spec=spec,
                    nonce=nonce_sha,
                )
                atomic_create_bytes(
                    out_dir / RUNTIME_RECEIPT_BASENAME, runtime_receipt_bytes
                )
            except BaseException:
                runtime_receipt = _unavailable_runtime_receipt(spec=spec, nonce=nonce_sha)
                status = "CHILD_FAILURE"
        if snapshot is not None and snapshot_bytes is not None:
            try:
                report = finalize_child_snapshot(
                    snapshot=snapshot,
                    audit_spec=spec,
                    parent_nonce_sha256=nonce_sha,
                    child_stdout=stdout,
                    child_stderr=stderr,
                    child_execution_status=status,
                    child_returncode=child_returncode,
                    runtime_receipt=runtime_receipt,
                )
                published_snapshot_bytes = snapshot_bytes
            except BaseException:
                status = "CHILD_FAILURE"
                fallback_snapshot = _failure_snapshot(
                    spec=spec, nonce=nonce_sha, status=status
                )
                report = finalize_child_snapshot(
                    snapshot=fallback_snapshot,
                    audit_spec=spec,
                    parent_nonce_sha256=nonce_sha,
                    child_stdout=stdout,
                    child_stderr=stderr,
                    child_execution_status=status,
                    child_returncode=child_returncode,
                    runtime_receipt=_unavailable_runtime_receipt(
                        spec=spec, nonce=nonce_sha
                    ),
                )
                published_snapshot_bytes = _canonical_json_bytes(fallback_snapshot)
        else:
            fallback_snapshot = _failure_snapshot(spec=spec, nonce=nonce_sha, status=status)
            report = finalize_child_snapshot(
                snapshot=fallback_snapshot,
                audit_spec=spec,
                parent_nonce_sha256=nonce_sha,
                child_stdout=stdout,
                child_stderr=stderr,
                child_execution_status=status,
                child_returncode=child_returncode,
                runtime_receipt=runtime_receipt,
            )
            published_snapshot_bytes = _canonical_json_bytes(fallback_snapshot)
    atomic_create_bytes(out_dir / SNAPSHOT_BASENAME, published_snapshot_bytes)
    artifact = build_stage_artifact(
        stage="G0",
        decision="G0_NO_GO",
        run_id=report["run_id"],
        reset_epoch=0,
        fixture_identity_sha256=report["fixture_identity_sha256"],
        treatment_sha256=canonical_json_sha256(spec),
        stage_evidence=build_stage_evidence(
            stage="G0",
            decision="G0_NO_GO",
            fixture_identity_sha256=report["fixture_identity_sha256"],
            treatment_sha256=canonical_json_sha256(spec),
            source_evidence=report,
        ),
        input_closure_sha256=report["fixture_identity_sha256"],
        forbidden_frozen_v6_input_count=0,
        predecessor_byte_hashes={},
    )
    atomic_create_bytes(out_dir / REPORT_BASENAME, _canonical_json_bytes(report))
    atomic_create_bytes(out_dir / ARTIFACT_BASENAME, serialize_stage_artifact(artifact))
    return 2


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", type=Path, default=DEFAULT_ASSET)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--timeout-s", type=float, default=180.0)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--nonce-sha256")
    parser.add_argument("--snapshot-out", type=Path)
    parser.add_argument("--runtime-receipt-out", type=Path)
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--experimental-profile-smoke", action="store_true")
    args = parser.parse_args(argv)
    if args.child:
        if (
            args.spec is None
            or args.nonce_sha256 is None
            or args.snapshot_out is None
            or args.runtime_receipt_out is None
        ):
            parser.error(
                "--child requires --spec, --nonce-sha256, --snapshot-out, and --runtime-receipt-out"
            )
        if args.experimental_profile_smoke:
            parser.error("--experimental-profile-smoke is parent-only")
    elif args.out_dir is None:
        parser.error("--out-dir is required")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.child:
        return _run_child(
            spec_path=args.spec,
            nonce=args.nonce_sha256,
            snapshot_path=args.snapshot_out,
            runtime_receipt_path=args.runtime_receipt_out,
            headless=args.headless,
        )
    experience_path = (
        EXPERIMENTAL_PROPERTY_QUERY_EXPERIENCE
        if args.experimental_profile_smoke
        else FORMAL_PROPERTY_QUERY_EXPERIENCE
    )
    return run_parent(
        asset_path=args.asset,
        out_dir=args.out_dir,
        timeout_s=args.timeout_s,
        experience_path=experience_path,
    )


if __name__ == "__main__":
    raise SystemExit(main())
