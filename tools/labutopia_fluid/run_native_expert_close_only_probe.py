#!/usr/bin/env python3
"""Launch and validate one production native-expert close-only attempt."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_PATH = REPO_ROOT / "main.py"
DEFAULT_CONFIG = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_native_expert_close_only_600hz_step600_layout_v1.yaml"
)
ASSET_PATH = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_level1_pour_interndata_contact_grasp_rest_offset_zero_step600_layout_v1.usda"
)
ROBOT_PATH = REPO_ROOT / "assets/robots/Franka.usd"
MAX_OBSERVATIONS = 2400
EXPECTED_PARTICLE_COUNT = 3600

EXPECTED_CONFIG_SHA256 = (
    "467596cb03a7f822215647a44cc63d379c72910a5bbf36df66ce3382df31dffe"
)
EXPECTED_ASSET_SHA256 = (
    "7c7667850dfc80a1d04c8649657cf9d9f5369b82e21f97b3d5c87c07ca218b02"
)
EXPECTED_ROBOT_SHA256 = (
    "312a326e338949fb40fd245886508cc52cc47e2bebd696e99c7dcdd3d3a7f90b"
)
EXPECTED_IMPLEMENTATION_SHA256 = {
    "main.py": "78433ba8f5d88d4c5a51e5cdb771dff804ad63bbf611ac0b3ec1455add313689",
    "controllers/base_controller.py": (
        "6e8c693065d43a5ae29954e8bbdec8da67a911e815f5198abb856c1e48811bf9"
    ),
    "controllers/pour_controller.py": (
        "be58f02fa54410f0d1705edfdfb6977d4f67de7e2777b39662c1f1effa96c8f1"
    ),
    "controllers/atomic_actions/pick_controller.py": (
        "eb08405bc8f538f2d2dd42dc2cf7b8aac660f73c0c0a4352e1ae9b8e25832b15"
    ),
    "robots/franka/franka.py": (
        "c406af2432eeb9bcefd4b4f0c0745f08afb54b635702878ae6c94f81a168f7a0"
    ),
    "robots/franka/rmpflow_controller.py": (
        "12464bf5294a39c8393332d6acc3dc38bb97b463f79a13406475a0ece1be9d7d"
    ),
    "utils/fluid_evaluation_loop.py": (
        "4fc56c25a283f396b0fa1dfde1b6ec7fbb6710cc0301c7c0d44fd35ee6ff137e"
    ),
    "utils/isaac_fluid_evaluation.py": (
        "bd7d3c3eea8c680bf443aac4bf3560df5a8bc327d26afb2366594f782ebd899a"
    ),
}

MANIFEST_TYPE = "native_expert_close_only_probe_v1"
PROBE_CONTROL_CONTRACT_ID = "contact_acquisition_probe_control_v1"
PROBE_CONTROL_CONTRACT_SCHEMA_VERSION = 1
PASS_DECISION = "NATIVE_EXPERT_CLOSE_ONLY_PASS"
FAIL_DECISION = "NATIVE_EXPERT_CLOSE_ONLY_FAIL"
RUNTIME_ERROR_DECISION = "PROBE_RUNTIME_ERROR"
FINAL_REPORT_BASENAME = "report.json"
EVIDENCE_DIR_BASENAME = "evidence"
EPISODE_JSONL_BASENAME = "episodes.jsonl"
OWNER_BASENAME = ".fluid-evidence-owner.json"
PARTITION_NAMES = (
    "source",
    "target",
    "transit",
    "tabletop_spill",
    "below_table",
    "nonfinite",
)
REQUIRED_PROBE_CHECKS = (
    "controller_completed",
    "collect_mode",
    "dynamic_source_ownership",
    "probe_execution_mode",
    "supported_control_profile",
    "profile_terminal_identity",
    "controller_close_command_emitted",
    "attachment_close_command_observed",
    "controller_lift_command_not_emitted",
    "attachment_lift_command_not_observed",
    "probe_qualified_now",
    "pour_forward_not_called",
    "pour_action_not_emitted",
    "terminal_outer_finished",
    "terminal_action_is_none",
    "dynamic_attachment_mode",
    "source_non_kinematic",
    "mechanical_attachment_not_used",
    "attachment_failure_free",
    "source_writer_audit_valid",
    "source_writer_audit_zero",
    "pour_not_started",
    "cumulative_containment_valid",
    "source_visual_sync_valid",
)


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_native(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _json_native(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [_json_native(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("close_only_json_nonfinite")
    return value


def _canonical_json_bytes(value: Any, *, indent: int | None = None) -> bytes:
    try:
        encoded = json.dumps(
            _json_native(value),
            allow_nan=False,
            indent=indent,
            separators=None if indent is not None else (",", ":"),
            sort_keys=True,
        )
    except ValueError as exc:
        raise ValueError("close_only_json_nonfinite") from exc
    return (encoded + "\n").encode("utf-8")


def _canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value).rstrip(b"\n")).hexdigest()


def atomic_create_json(
    path: str | os.PathLike[str],
    value: Mapping[str, Any],
) -> None:
    """Publish one complete report without replacing an existing result."""
    if not isinstance(value, Mapping):
        raise TypeError("close_only_json_mapping_required")
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_json_bytes(value, indent=2)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary_path, output_path)
        except FileExistsError as exc:
            raise FileExistsError(f"close_only_output_exists:{output_path}") from exc
        directory_descriptor = os.open(output_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary_path.unlink(missing_ok=True)


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_key:{key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"nonfinite_constant:{value}")


def _validate_json_tree(value: Any) -> None:
    if isinstance(value, Mapping):
        for item in value.values():
            _validate_json_tree(item)
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_tree(item)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite_number")


def _load_exact_jsonl_object(path: Path, *, error_code: str) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
        if (
            not payload
            or not payload.endswith(b"\n")
            or b"\n" in payload[:-1]
            or b"\r" in payload
        ):
            raise ValueError("line_contract")
        line = payload[:-1]
        if not line.strip():
            raise ValueError("blank_line")
        decoded = line.decode("utf-8", errors="strict")
        result = json.loads(
            decoded,
            object_pairs_hook=_strict_object_pairs,
            parse_constant=_reject_json_constant,
        )
        if not isinstance(result, dict):
            raise TypeError("mapping_required")
        _validate_json_tree(result)
        return result
    except (OSError, TypeError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{error_code}:{path}") from exc


def load_terminal_episode(path: str | os.PathLike[str]) -> dict[str, Any]:
    return _load_exact_jsonl_object(
        Path(path),
        error_code="close_only_terminal_jsonl_invalid",
    )


def load_evidence_owner(path: str | os.PathLike[str]) -> dict[str, Any]:
    owner = _load_exact_jsonl_object(
        Path(path),
        error_code="close_only_owner_json_invalid",
    )
    if set(owner) != {"pid", "run_id"}:
        raise ValueError("close_only_evidence_identity_invalid")
    return owner


def validate_evidence_identity(
    owner: Mapping[str, Any],
    episode: Mapping[str, Any],
    *,
    expected_child_pid: int,
) -> dict[str, Any]:
    owner_pid = owner.get("pid")
    owner_run_id = owner.get("run_id")
    episode_run_id = episode.get("run_id")
    if (
        set(owner) != {"pid", "run_id"}
        or type(expected_child_pid) is not int
        or expected_child_pid <= 0
        or type(owner_pid) is not int
        or owner_pid <= 0
        or owner_pid != expected_child_pid
        or not isinstance(owner_run_id, str)
        or not owner_run_id
        or not isinstance(episode_run_id, str)
        or episode_run_id != owner_run_id
    ):
        raise ValueError("close_only_evidence_identity_invalid")
    return {"pid": owner_pid, "run_id": owner_run_id, "valid": True}


def _required_mapping(
    value: Mapping[str, Any],
    name: str,
    *,
    error_code: str,
) -> Mapping[str, Any]:
    result = value.get(name)
    if not isinstance(result, Mapping):
        raise ValueError(error_code)
    return result


def _required_bool(
    value: Mapping[str, Any],
    name: str,
    *,
    error_code: str,
) -> bool:
    result = value.get(name)
    if type(result) is not bool:
        raise ValueError(error_code)
    return result


def _required_nonempty_string(
    value: Mapping[str, Any],
    name: str,
    *,
    error_code: str,
) -> str:
    result = value.get(name)
    if not isinstance(result, str) or not result:
        raise ValueError(error_code)
    return result


def _validate_probe_control_contract(
    episode: Mapping[str, Any],
) -> tuple[dict[str, bool], bool]:
    error_code = "close_only_probe_control_contract_invalid"
    contract = _required_mapping(
        episode,
        "probe_control_contract",
        error_code=error_code,
    )
    if (
        set(contract)
        != {
            "id",
            "schema_version",
            "supported_control_profiles",
            "selected_control_profile",
            "checks",
            "valid",
        }
        or contract.get("id") != PROBE_CONTROL_CONTRACT_ID
        or contract.get("schema_version") != PROBE_CONTROL_CONTRACT_SCHEMA_VERSION
        or contract.get("supported_control_profiles")
        != ["native_expert_v1", "contact_pick_v1"]
        or contract.get("selected_control_profile") != "native_expert_v1"
        or type(contract.get("valid")) is not bool
    ):
        raise ValueError(error_code)
    raw_checks = contract.get("checks")
    if not isinstance(raw_checks, Mapping) or set(raw_checks) != set(
        REQUIRED_PROBE_CHECKS
    ):
        raise ValueError(error_code)
    checks = {name: raw_checks[name] for name in REQUIRED_PROBE_CHECKS}
    if any(type(value) is not bool for value in checks.values()):
        raise ValueError(error_code)
    valid = bool(contract["valid"])
    if valid is not all(checks.values()):
        raise ValueError(error_code)

    control = _required_mapping(
        episode,
        "control",
        error_code="close_only_terminal_episode_invalid",
    )
    attachment = _required_mapping(
        episode,
        "attachment",
        error_code="close_only_terminal_episode_invalid",
    )
    native_pick = _required_mapping(
        control,
        "native_pick",
        error_code="close_only_terminal_episode_invalid",
    )
    writer_audit = _required_mapping(
        attachment,
        "source_writer_audit",
        error_code="close_only_terminal_episode_invalid",
    )
    cumulative = _required_mapping(
        episode,
        "cumulative_containment",
        error_code="close_only_terminal_episode_invalid",
    )

    if (
        control.get("mode") != "collect"
        or control.get("source_ownership") != "contact_friction_dynamic_v1"
        or control.get("expert_control_profile") != "native_expert_v1"
        or control.get("execution_mode") != "contact_acquisition_probe_v1"
        or control.get("contact_pick") is not None
        or type(control.get("contact_acquisition_probe")) is not bool
        or type(control.get("contact_grasp_required")) is not bool
        or (
            native_pick.get("last_emitted_event") is not None
            and (
                type(native_pick.get("last_emitted_event")) is not int
                or native_pick["last_emitted_event"] < 0
            )
        )
        or type(native_pick.get("close_command_emitted")) is not bool
        or type(native_pick.get("lift_command_emitted")) is not bool
        or type(control.get("pour_forward_invocation_count")) is not int
        or control["pour_forward_invocation_count"] < 0
        or type(attachment.get("source_dynamic")) is not bool
        or type(attachment.get("mechanical_attachment_used")) is not bool
        or type(attachment.get("kinematic_target_update_count")) is not int
        or attachment["kinematic_target_update_count"] < 0
        or type(attachment.get("close_command_observed")) is not bool
        or type(attachment.get("lift_command_observed")) is not bool
        or type(attachment.get("probe_qualified_now")) is not bool
        or "failure_reason" not in attachment
        or (
            attachment.get("failure_reason") is not None
            and not isinstance(attachment.get("failure_reason"), str)
        )
        or type(writer_audit.get("coverage_complete")) is not bool
        or type(writer_audit.get("valid")) is not bool
        or type(writer_audit.get("call_count")) is not int
        or writer_audit["call_count"] < 0
        or "pour_started_physics_step" not in cumulative
        or (
            cumulative.get("pour_started_physics_step") is not None
            and (
                type(cumulative.get("pour_started_physics_step")) is not int
                or cumulative["pour_started_physics_step"] < 0
            )
        )
    ):
        raise ValueError("close_only_terminal_episode_invalid")

    controller_completed = _required_bool(
        episode,
        "controller_completed",
        error_code="close_only_terminal_episode_invalid",
    )
    cumulative_containment_valid = _required_bool(
        episode,
        "cumulative_containment_valid",
        error_code="close_only_terminal_episode_invalid",
    )
    source_visual_sync_valid = _required_bool(
        episode,
        "source_visual_sync_valid",
        error_code="close_only_terminal_episode_invalid",
    )
    expected_checks = {
        "controller_completed": controller_completed is True,
        "collect_mode": control.get("mode") == "collect",
        "dynamic_source_ownership": (
            control.get("source_ownership") == "contact_friction_dynamic_v1"
        ),
        "probe_execution_mode": (
            control.get("execution_mode") == "contact_acquisition_probe_v1"
            and control.get("contact_acquisition_probe") is True
            and control.get("contact_grasp_required") is True
        ),
        "supported_control_profile": True,
        "profile_terminal_identity": native_pick.get("last_emitted_event") == 4,
        "controller_close_command_emitted": (
            native_pick.get("close_command_emitted") is True
        ),
        "attachment_close_command_observed": (
            attachment.get("close_command_observed") is True
        ),
        "controller_lift_command_not_emitted": (
            native_pick.get("lift_command_emitted") is False
            and native_pick.get("last_emitted_event") == 4
        ),
        "attachment_lift_command_not_observed": (
            attachment.get("lift_command_observed") is False
        ),
        "probe_qualified_now": attachment.get("probe_qualified_now") is True,
        "pour_forward_not_called": (
            control.get("pour_forward_invocation_count") == 0
        ),
        "pour_action_not_emitted": (
            control.get("pour_forward_invocation_count") == 0
        ),
        "dynamic_attachment_mode": (
            attachment.get("mode") == "contact_friction_dynamic_v1"
            and attachment.get("source_dynamic") is True
        ),
        "source_non_kinematic": (
            attachment.get("kinematic_target_update_count") == 0
        ),
        "mechanical_attachment_not_used": (
            attachment.get("mechanical_attachment_used") is False
        ),
        "attachment_failure_free": attachment.get("failure_reason") is None,
        "source_writer_audit_valid": (
            writer_audit.get("coverage_complete") is True
            and writer_audit.get("valid") is True
        ),
        "source_writer_audit_zero": (
            writer_audit.get("call_count") == 0
        ),
        "pour_not_started": cumulative.get("pour_started_physics_step") is None,
        "cumulative_containment_valid": cumulative_containment_valid is True,
        "source_visual_sync_valid": source_visual_sync_valid is True,
    }
    for name, expected in expected_checks.items():
        if checks[name] is not expected:
            raise ValueError("close_only_probe_control_checks_mismatch")
    return checks, valid


def _validate_termination(
    episode: Mapping[str, Any],
) -> int:
    error_code = "close_only_termination_contract_invalid"
    termination = _required_mapping(
        episode,
        "termination",
        error_code=error_code,
    )
    per_episode_hit = _required_bool(
        termination,
        "max_observations_per_episode_reached",
        error_code=error_code,
    )
    global_hit = _required_bool(
        termination,
        "max_fluid_observations_reached",
        error_code=error_code,
    )
    observation_count = termination.get("observation_count")
    if (
        type(observation_count) is not int
        or not 1 <= observation_count <= MAX_OBSERVATIONS
    ):
        raise ValueError(error_code)
    expected_limit_hit = observation_count == MAX_OBSERVATIONS
    if per_episode_hit is not expected_limit_hit or global_hit is not expected_limit_hit:
        raise ValueError(error_code)
    expected_reason = (
        "max_observations_per_episode_reached" if expected_limit_hit else None
    )

    boundary = _required_mapping(
        termination,
        "observation_limit_boundary",
        error_code=error_code,
    )
    boundary_reached = _required_bool(
        boundary,
        "reached",
        error_code=error_code,
    )
    if (
        boundary_reached is not expected_limit_hit
        or boundary.get("reason") != expected_reason
    ):
        raise ValueError(error_code)

    limit_termination = _required_mapping(
        termination,
        "observation_limit_termination",
        error_code=error_code,
    )
    terminated = _required_bool(
        limit_termination,
        "terminated",
        error_code=error_code,
    )
    if terminated:
        if not expected_limit_hit or limit_termination.get("reason") != expected_reason:
            raise ValueError(error_code)
    elif limit_termination.get("reason") is not None:
        raise ValueError(error_code)

    terminal = _required_mapping(
        episode,
        "terminal_observation",
        error_code=error_code,
    )
    if (
        terminal.get("episode_id") != episode.get("episode_id")
        or terminal.get("observation_index") != observation_count - 1
        or not isinstance(terminal.get("frame_identity"), str)
        or not terminal["frame_identity"]
    ):
        raise ValueError(error_code)
    return observation_count


def _validate_final_particle_counts(episode: Mapping[str, Any]) -> None:
    error_code = "close_only_particle_counts_invalid"
    counts = _required_mapping(
        episode,
        "final_particle_counts",
        error_code=error_code,
    )
    if set(counts) != set(PARTITION_NAMES):
        raise ValueError(error_code)
    values = [counts[name] for name in PARTITION_NAMES]
    if (
        any(type(value) is not int or value < 0 for value in values)
        or sum(values) != EXPECTED_PARTICLE_COUNT
    ):
        raise ValueError(error_code)


def validate_terminal_episode(
    episode: Mapping[str, Any],
    *,
    expected_run_id: str,
) -> dict[str, Any]:
    if not isinstance(episode, Mapping):
        raise TypeError("close_only_terminal_episode_mapping_required")
    error_code = "close_only_terminal_episode_invalid"
    run_id = _required_nonempty_string(episode, "run_id", error_code=error_code)
    attempt_id = _required_nonempty_string(
        episode, "attempt_id", error_code=error_code
    )
    episode_id = _required_nonempty_string(
        episode, "episode_id", error_code=error_code
    )
    attempt_status = episode.get("attempt_status")
    if (
        not isinstance(expected_run_id, str)
        or not expected_run_id
        or run_id != expected_run_id
        or attempt_status not in {"completed", "failed"}
        or episode.get("acceptance_mode") != "contact_acquisition_probe_v1"
    ):
        raise ValueError(error_code)

    _checks, contract_valid = _validate_probe_control_contract(episode)
    accepted = _required_bool(
        episode,
        "contact_acquisition_probe_accepted",
        error_code=error_code,
    )
    success = _required_bool(episode, "success", error_code=error_code)
    expert_accepted = _required_bool(
        episode,
        "expert_episode_accepted",
        error_code=error_code,
    )
    controller_completed = _required_bool(
        episode,
        "controller_completed",
        error_code=error_code,
    )
    if (
        accepted is not contract_valid
        or success is not accepted
        or expert_accepted is not False
        or (accepted and (attempt_status != "completed" or not controller_completed))
    ):
        raise ValueError(error_code)

    observation_count = _validate_termination(episode)
    _validate_final_particle_counts(episode)
    return {
        "measurement_decision": PASS_DECISION if accepted else FAIL_DECISION,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "episode_id": episode_id,
        "attempt_status": attempt_status,
        "observation_count": observation_count,
        "probe_control_contract_id": PROBE_CONTROL_CONTRACT_ID,
        "probe_control_contract_schema_version": (
            PROBE_CONTROL_CONTRACT_SCHEMA_VERSION
        ),
        "probe_control_contract_valid": contract_valid,
    }


def build_child_command(
    *,
    config_path: str | os.PathLike[str],
    evidence_dir: str | os.PathLike[str],
    python_executable: str | os.PathLike[str] = sys.executable,
) -> list[str]:
    config = Path(config_path).resolve()
    evidence = Path(evidence_dir).resolve()
    config_dir = os.path.relpath(config.parent, REPO_ROOT)
    return [
        str(Path(python_executable).resolve()),
        str(MAIN_PATH.resolve()),
        "--backend",
        "gpu",
        "--headless",
        "--no-video",
        "--config-name",
        config.stem,
        "--config-dir",
        config_dir,
        "--fluid-evidence-dir",
        str(evidence),
        "--max-fluid-observations",
        str(MAX_OBSERVATIONS),
    ]


def validate_run_identity(identity: Mapping[str, Any]) -> dict[str, Any]:
    error_code = "close_only_run_identity_invalid"
    if not isinstance(identity, Mapping):
        raise TypeError(error_code)
    if set(identity) != {
        "schema_version",
        "python_executable",
        "config",
        "asset",
        "robot",
        "implementation",
        "identity_sha256",
    }:
        raise ValueError(error_code)
    if identity.get("schema_version") != 1:
        raise ValueError(error_code)
    python_executable = identity.get("python_executable")
    if (
        not isinstance(python_executable, str)
        or Path(python_executable).resolve() != Path(sys.executable).resolve()
    ):
        raise ValueError(error_code)

    expected_hashes = {
        "config": EXPECTED_CONFIG_SHA256,
        "asset": EXPECTED_ASSET_SHA256,
        "robot": EXPECTED_ROBOT_SHA256,
    }
    for name, expected_hash in expected_hashes.items():
        record = identity.get(name)
        if (
            not isinstance(record, Mapping)
            or set(record) != {"path", "sha256"}
            or not isinstance(record.get("path"), str)
            or record.get("sha256") != expected_hash
        ):
            raise ValueError(error_code)

    implementation = identity.get("implementation")
    if not isinstance(implementation, Mapping) or set(implementation) != {
        "files",
        "closure_sha256",
    }:
        raise ValueError(error_code)
    files = implementation.get("files")
    if files != EXPECTED_IMPLEMENTATION_SHA256:
        raise ValueError(error_code)
    expected_closure = _canonical_json_sha256(EXPECTED_IMPLEMENTATION_SHA256)
    if implementation.get("closure_sha256") != expected_closure:
        raise ValueError(error_code)

    payload = {key: value for key, value in identity.items() if key != "identity_sha256"}
    if identity.get("identity_sha256") != _canonical_json_sha256(payload):
        raise ValueError(error_code)
    return dict(identity)


def build_run_identity(
    config_path: str | os.PathLike[str] = DEFAULT_CONFIG,
) -> dict[str, Any]:
    config = Path(config_path).resolve()
    implementation_hashes = {
        relative_path: sha256_file(REPO_ROOT / relative_path)
        for relative_path in EXPECTED_IMPLEMENTATION_SHA256
    }
    observed_hashes = {
        "config": sha256_file(config),
        "asset": sha256_file(ASSET_PATH),
        "robot": sha256_file(ROBOT_PATH),
    }
    if (
        observed_hashes["config"] != EXPECTED_CONFIG_SHA256
        or observed_hashes["asset"] != EXPECTED_ASSET_SHA256
        or observed_hashes["robot"] != EXPECTED_ROBOT_SHA256
        or implementation_hashes != EXPECTED_IMPLEMENTATION_SHA256
    ):
        raise ValueError("close_only_run_identity_hash_mismatch")
    payload = {
        "schema_version": 1,
        "python_executable": str(Path(sys.executable).resolve()),
        "config": {"path": str(config), "sha256": observed_hashes["config"]},
        "asset": {
            "path": str(ASSET_PATH.resolve()),
            "sha256": observed_hashes["asset"],
        },
        "robot": {
            "path": str(ROBOT_PATH.resolve()),
            "sha256": observed_hashes["robot"],
        },
        "implementation": {
            "files": implementation_hashes,
            "closure_sha256": _canonical_json_sha256(implementation_hashes),
        },
    }
    return validate_run_identity(
        {**payload, "identity_sha256": _canonical_json_sha256(payload)}
    )


def terminate_process_group(
    process: subprocess.Popen[Any],
    *,
    term_grace_seconds: float = 30.0,
    kill_grace_seconds: float = 10.0,
) -> str:
    if process.poll() is not None:
        process.wait(timeout=kill_grace_seconds)
        return "ALREADY_EXITED"
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=term_grace_seconds)
        return "SIGTERM"
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=kill_grace_seconds)
            return "SIGKILL"
        except subprocess.TimeoutExpired:
            return "SIGKILL_UNREAPED"


def finalize_probe_report(
    *,
    terminal_validation: Mapping[str, Any] | None,
    run_identity: Mapping[str, Any],
    child_command: Sequence[str],
    child_returncode: int,
    timed_out: bool,
    termination: str | None,
    runtime_error: str | None,
) -> dict[str, Any]:
    if type(child_returncode) is not int or type(timed_out) is not bool:
        raise ValueError("close_only_child_status_invalid")
    pre_shutdown_decision = (
        terminal_validation.get("measurement_decision")
        if isinstance(terminal_validation, Mapping)
        else RUNTIME_ERROR_DECISION
    )
    if pre_shutdown_decision not in {PASS_DECISION, FAIL_DECISION}:
        pre_shutdown_decision = RUNTIME_ERROR_DECISION
    clean = bool(
        not timed_out
        and child_returncode == 0
        and runtime_error is None
        and isinstance(terminal_validation, Mapping)
        and pre_shutdown_decision in {PASS_DECISION, FAIL_DECISION}
    )
    report = {
        "schema_version": 1,
        "manifest_type": MANIFEST_TYPE,
        "finalized_at_utc": datetime.now(timezone.utc).isoformat(),
        "pre_shutdown_decision": pre_shutdown_decision,
        "run_identity": dict(run_identity),
        "terminal_validation": (
            dict(terminal_validation)
            if isinstance(terminal_validation, Mapping)
            else None
        ),
        "child_process": {
            "command": [str(value) for value in child_command],
            "returncode": child_returncode,
            "timed_out": timed_out,
            "termination": termination,
        },
        "runtime_error": runtime_error,
    }
    if clean:
        report.update(
            {
                "decision": pre_shutdown_decision,
                "lifecycle_status": "completed",
                "shutdown_status": "child_exit_0",
            }
        )
        return report

    if timed_out:
        shutdown_status = "child_timeout"
    elif runtime_error is not None and runtime_error.startswith("child_launch_error"):
        shutdown_status = "child_launch_error"
    elif runtime_error is not None and runtime_error.startswith("identity_"):
        shutdown_status = "identity_validation_failed"
    elif child_returncode != 0:
        shutdown_status = "child_exit_nonzero"
    elif runtime_error is not None:
        shutdown_status = "evidence_validation_failed"
    else:
        shutdown_status = "measurement_runtime_error"
    report.update(
        {
            "decision": RUNTIME_ERROR_DECISION,
            "lifecycle_status": "failed",
            "shutdown_status": shutdown_status,
        }
    )
    return report


def _artifact_record(path: Path, *, relative_to: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(relative_to)),
        "byte_count": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _run_parent(args: argparse.Namespace) -> int:
    try:
        args.out_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        print(
            f"native expert close-only probe refused existing output: {args.out_dir}",
            file=sys.stderr,
            flush=True,
        )
        return 2

    evidence_dir = args.out_dir / EVIDENCE_DIR_BASENAME
    command = build_child_command(
        config_path=args.config,
        evidence_dir=evidence_dir,
    )
    stdout_path = args.out_dir / "child.stdout.log"
    stderr_path = args.out_dir / "child.stderr.log"
    run_identity: Mapping[str, Any] = {
        "schema_version": 1,
        "status": "unavailable",
    }
    terminal_validation: Mapping[str, Any] | None = None
    runtime_error: str | None = None
    timed_out = False
    termination = None
    child_returncode = 127
    process: subprocess.Popen[Any] | None = None
    child_pid: int | None = None
    phase = "identity_preflight"

    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        try:
            preflight_identity = build_run_identity(args.config)
            run_identity = preflight_identity
            phase = "child_launch"
            process = subprocess.Popen(
                command,
                cwd=str(REPO_ROOT),
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            child_pid = int(process.pid)
            phase = "child_wait"
            try:
                child_returncode = int(
                    process.wait(timeout=args.timeout_seconds)
                )
            except subprocess.TimeoutExpired:
                timed_out = True
                runtime_error = "child_timeout"
                termination = terminate_process_group(process)
                child_returncode = (
                    int(process.returncode)
                    if process.returncode is not None
                    else -signal.SIGKILL
                )

            if not timed_out and child_returncode != 0:
                runtime_error = f"child_exit_nonzero:{child_returncode}"
            if runtime_error is None:
                phase = "identity_postflight"
                postflight_identity = build_run_identity(args.config)
                if postflight_identity != preflight_identity:
                    raise ValueError("identity_changed_during_run")
                phase = "evidence_validation"
                owner = load_evidence_owner(evidence_dir / OWNER_BASENAME)
                episode = load_terminal_episode(
                    evidence_dir / EPISODE_JSONL_BASENAME
                )
                evidence_identity = validate_evidence_identity(
                    owner,
                    episode,
                    expected_child_pid=child_pid,
                )
                terminal_validation = validate_terminal_episode(
                    episode,
                    expected_run_id=evidence_identity["run_id"],
                )
        except BaseException as exc:
            if process is not None and process.poll() is None:
                try:
                    termination = terminate_process_group(process)
                except BaseException as cleanup_exc:
                    termination = f"CLEANUP_ERROR:{type(cleanup_exc).__name__}"
            if process is not None and process.returncode is not None:
                child_returncode = int(process.returncode)
            runtime_error = f"{phase}_error:{type(exc).__name__}:{exc}"

    report = finalize_probe_report(
        terminal_validation=terminal_validation,
        run_identity=run_identity,
        child_command=command,
        child_returncode=child_returncode,
        timed_out=timed_out,
        termination=termination,
        runtime_error=runtime_error,
    )
    artifacts: dict[str, Any] = {
        "child_stdout": _artifact_record(stdout_path, relative_to=args.out_dir),
        "child_stderr": _artifact_record(stderr_path, relative_to=args.out_dir),
    }
    for name, path in (
        ("evidence_owner", evidence_dir / OWNER_BASENAME),
        ("terminal_episode", evidence_dir / EPISODE_JSONL_BASENAME),
        ("observations", evidence_dir / "observations.jsonl"),
    ):
        if path.is_file():
            artifacts[name] = _artifact_record(path, relative_to=args.out_dir)
    report["artifacts"] = artifacts
    final_path = args.out_dir / FINAL_REPORT_BASENAME
    atomic_create_json(final_path, report)
    print(
        f"native expert close-only probe decision={report['decision']} out={final_path}",
        flush=True,
    )
    return 0 if report["lifecycle_status"] == "completed" else 2


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=1200.0)
    args = parser.parse_args(argv)
    args.config = args.config.resolve()
    args.out_dir = args.out_dir.resolve()
    if not args.config.is_file():
        parser.error(f"config not found: {args.config}")
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0.0:
        parser.error("timeout must be finite and positive")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    return _run_parent(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
