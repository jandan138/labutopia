#!/usr/bin/env python3
"""Run the original empty-beaker contact-lift three-treatment causal probe."""

from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import math
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import time
import traceback
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_CONFIG = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_original_empty_contact_lift_v1.yaml"
)
PRODUCTION_CONFIG = REPO_ROOT / "config/level1_pour.yaml"
TREATMENTS = (
    "control",
    "instrumented_original",
    "zero_friction_ablation",
)
DECISIONS = (
    "PROBE_RUNTIME_ERROR",
    "PROBE_PROTOCOL_NO_GO",
    "CONTACT_REPORT_PERTURBATION_NO_GO",
    "ORIGINAL_EMPTY_BEAKER_CONTACT_LIFT_FAIL",
    "EMPTY_BEAKER_RETENTION_CONTINUATION_FAIL",
    "ZERO_FRICTION_CAUSALITY_FAIL",
    "ORIGINAL_EMPTY_BEAKER_FRICTION_CAUSAL_PASS",
)
ACTION_CHANNELS = (
    "joint_positions",
    "joint_velocities",
    "joint_efforts",
)
REQUIRED_AUDIT_SURFACES = (
    "object_utils_root_pose_velocity",
    "object_utils_body_pose_velocity",
    "rigid_prim_singular_pose_velocity",
    "rigid_prim_plural_pose_velocity",
    "physics_view_kinematic_targets",
    "rigid_body_force_torque_impulse",
    "physics_view_force_at_position",
    "tensor_force_torque_impulse",
    "raw_source_properties",
    "physx_force_api",
    "force_field_membership",
    "software_gripper_add_update_release",
    "usd_runtime_constraints_attachments",
    "forward_filtered_pairs",
    "reverse_filtered_pairs",
    "collision_groups_masks_merge_groups",
)
MANIFEST_TYPE = "original_empty_beaker_contact_lift_probe_v1"
CHILD_MANIFEST_TYPE = "original_empty_beaker_contact_lift_child_v1"
TRACE_MANIFEST_TYPE = "original_empty_beaker_contact_lift_trace_record_v1"
PROVISIONAL_REPORT_BASENAME = "provisional_report.json"
TRACE_BASENAME = "trace.jsonl"
CLEANUP_BASENAME = "cleanup.json"
FINAL_REPORT_BASENAME = "report.json"
FROZEN_CONFIG_BASENAME = "frozen_config.json"
_ZERO_SHA256 = "0" * 64
_PROTO_NONE = 0xFFFFFFFF


class ProtocolBlocker(RuntimeError):
    """A measured lack of protocol authority, not an application crash."""

    def __init__(self, code: str, detail: str, *, evidence: Any = None) -> None:
        if not isinstance(code, str) or not code:
            raise ValueError("probe_blocker_code_invalid")
        if not isinstance(detail, str) or not detail:
            raise ValueError("probe_blocker_detail_invalid")
        super().__init__(f"{code}:{detail}")
        self.code = code
        self.detail = detail
        self.evidence = evidence


def _is_sha256(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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
    if isinstance(value, np.ndarray):
        return _json_native(value.tolist())
    if isinstance(value, np.generic):
        return _json_native(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("probe_json_nonfinite")
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
    except (TypeError, ValueError) as exc:
        if "probe_json_nonfinite" in str(exc):
            raise
        raise ValueError("probe_json_invalid") from exc
    return (encoded + "\n").encode("utf-8")


def _canonical_json_sha256(value: Any) -> str:
    return _sha256_bytes(_canonical_json_bytes(value).rstrip(b"\n"))


def _publish_create_only(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary_path, path)
        except FileExistsError as exc:
            raise FileExistsError(f"probe_output_exists:{path}") from exc
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary_path.unlink(missing_ok=True)


def atomic_create_json(
    path: str | os.PathLike[str], value: Mapping[str, Any]
) -> None:
    if not isinstance(value, Mapping):
        raise TypeError("probe_json_mapping_required")
    _publish_create_only(Path(path), _canonical_json_bytes(value, indent=2))


def atomic_create_jsonl(
    path: str | os.PathLike[str], records: Sequence[Mapping[str, Any]]
) -> None:
    if isinstance(records, (str, bytes, bytearray)) or not isinstance(
        records, Sequence
    ):
        raise TypeError("probe_jsonl_sequence_required")
    payload = b"".join(_canonical_json_bytes(record) for record in records)
    if not payload:
        raise ValueError("probe_jsonl_records_required")
    _publish_create_only(Path(path), payload)


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_key:{key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"nonfinite_constant:{value}")


def _validate_finite_json_tree(value: Any) -> None:
    if isinstance(value, Mapping):
        for item in value.values():
            _validate_finite_json_tree(item)
    elif isinstance(value, list):
        for item in value:
            _validate_finite_json_tree(item)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite_number")


def _decode_strict_json_line(line: bytes) -> dict[str, Any]:
    try:
        decoded = line.decode("utf-8", errors="strict")
        value = json.loads(
            decoded,
            object_pairs_hook=_strict_object_pairs,
            parse_constant=_reject_json_constant,
        )
        if not isinstance(value, dict):
            raise TypeError("mapping_required")
        _validate_finite_json_tree(value)
        return value
    except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("probe_strict_json_invalid") from exc


def load_strict_json_object(path: str | os.PathLike[str]) -> dict[str, Any]:
    try:
        payload = Path(path).read_bytes()
    except OSError as exc:
        raise ValueError("probe_strict_json_invalid") from exc
    if (
        not payload
        or not payload.endswith(b"\n")
        or b"\r" in payload
        or payload.endswith(b"\n\n")
    ):
        raise ValueError("probe_strict_json_invalid")
    return _decode_strict_json_line(payload[:-1])


def load_strict_jsonl(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    try:
        payload = Path(path).read_bytes()
    except OSError as exc:
        raise ValueError("probe_strict_jsonl_invalid") from exc
    if not payload or not payload.endswith(b"\n") or b"\r" in payload:
        raise ValueError("probe_strict_jsonl_invalid")
    lines = payload[:-1].split(b"\n")
    if not lines or any(not line.strip() for line in lines):
        raise ValueError("probe_strict_jsonl_invalid")
    try:
        return [_decode_strict_json_line(line) for line in lines]
    except ValueError as exc:
        raise ValueError("probe_strict_jsonl_invalid") from exc


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_yaml_mapping(loader: Any, node: Any, deep: bool = False) -> dict:
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"probe_yaml_duplicate_key:{key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_yaml_mapping,
)


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
        raise ValueError(f"probe_config_parse_invalid:{path}") from exc
    if not isinstance(value, dict):
        raise ValueError("probe_config_mapping_required")
    _validate_finite_json_tree(value)
    return value


def production_visible_projection(config: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(config, Mapping):
        raise TypeError("probe_config_mapping_required")
    projected = copy.deepcopy(dict(config))
    for field in ("diagnostic", "name", "max_episodes", "hydra", "multi_run"):
        projected.pop(field, None)
    return json.loads(_canonical_json_bytes(projected).decode("utf-8"))


def _validate_relative_output_route(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("probe_config_output_route_invalid")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path == Path("."):
        raise ValueError("probe_config_output_route_invalid")
    return value


def freeze_diagnostic_config(
    config_path: str | os.PathLike[str],
    *,
    production_config_path: str | os.PathLike[str] = PRODUCTION_CONFIG,
) -> dict[str, Any]:
    path = Path(config_path).resolve()
    production_path = Path(production_config_path).resolve()
    config = _load_yaml_mapping(path)
    production = _load_yaml_mapping(production_path)
    diagnostic = config.get("diagnostic")
    if not isinstance(diagnostic, Mapping):
        raise ValueError("probe_config_diagnostic_missing")
    required = {
        "schema_version": 1,
        "protocol_id": "original_empty_beaker_contact_lift_v1",
        "treatments": list(TREATMENTS),
        "numpy_seed": 20260717,
        "maximum_production_steps": 1500,
        "child_timeout_seconds": 240,
        "retention_steps": 60,
        "physics_context_path": "/physicsScene",
        "physics_scene_paths_in_traversal_order": [
            "/physicsScene",
            "/World/PhysicsScene",
        ],
        "source_reset_root_path": "/World/beaker2",
        "source_body_path": "/World/beaker2/mesh",
        "source_collider_path": "/World/beaker2/mesh",
        "support_collider_path": "/World/Cube",
        "left_finger_body_path": "/World/Franka/panda_leftfinger",
        "right_finger_body_path": "/World/Franka/panda_rightfinger",
        "native_finger_joint_target_m": 0.028,
        "native_lift_target_m": 0.5,
    }
    if any(diagnostic.get(key) != value for key, value in required.items()):
        raise ValueError("probe_config_pinned_contract_mismatch")
    if (
        not math.isclose(
            float(diagnostic.get("physics_dt", math.nan)),
            1.0 / 60.0,
            rel_tol=0.0,
            abs_tol=0.0,
        )
        or diagnostic.get("gravity_world_m_s2") != [0.0, 0.0, -9.81]
        or config.get("usd_path")
        != "assets/chemistry_lab/lab_001/lab_001.usd"
        or config.get("max_episodes") != 1
        or "usd_path" in config.get("robot", {})
    ):
        raise ValueError("probe_config_pinned_contract_mismatch")
    multi_run = config.get("multi_run")
    hydra = config.get("hydra")
    if not isinstance(multi_run, Mapping) or not isinstance(hydra, Mapping):
        raise ValueError("probe_config_output_route_invalid")
    run = hydra.get("run")
    if not isinstance(run, Mapping):
        raise ValueError("probe_config_output_route_invalid")
    multi_route = _validate_relative_output_route(multi_run.get("run_dir"))
    hydra_route = _validate_relative_output_route(run.get("dir"))
    if multi_route != "collector" or hydra_route != "hydra":
        raise ValueError("probe_config_output_route_invalid")
    projection = production_visible_projection(config)
    production_projection = production_visible_projection(production)
    if projection != production_projection:
        raise ValueError("probe_config_production_projection_mismatch")
    canonical = _canonical_json_bytes(config)
    return {
        "config": config,
        "canonical_bytes": canonical,
        "sha256": _sha256_bytes(canonical),
        "source_path": str(path),
        "source_sha256": sha256_file(path),
        "production_path": str(production_path),
        "production_sha256": sha256_file(production_path),
        "production_projection_sha256": _canonical_json_sha256(projection),
    }


def write_frozen_config(
    canonical_bytes: bytes, treatment_dir: str | os.PathLike[str]
) -> Path:
    if not isinstance(canonical_bytes, bytes) or not canonical_bytes.endswith(b"\n"):
        raise ValueError("probe_frozen_config_bytes_invalid")
    config = _decode_strict_json_line(canonical_bytes[:-1])
    if _canonical_json_bytes(config) != canonical_bytes:
        raise ValueError("probe_frozen_config_not_canonical")
    directory = Path(treatment_dir).resolve()
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(directory, 0o700)
    path = directory / FROZEN_CONFIG_BASENAME
    _publish_create_only(path, canonical_bytes)
    os.chmod(path, 0o600)
    return path


def build_child_command(
    *,
    treatment: str,
    frozen_config_path: str | os.PathLike[str],
    treatment_dir: str | os.PathLike[str],
    run_nonce: str,
    parent_pid: int,
    expected_config_sha256: str,
    python_executable: str | os.PathLike[str] = sys.executable,
) -> list[str]:
    if treatment not in TREATMENTS:
        raise ValueError("probe_treatment_invalid")
    if not isinstance(run_nonce, str) or not run_nonce:
        raise ValueError("probe_run_nonce_invalid")
    if type(parent_pid) is not int or parent_pid <= 0:
        raise ValueError("probe_parent_pid_invalid")
    if not _is_sha256(expected_config_sha256):
        raise ValueError("probe_config_sha256_invalid")
    return [
        str(Path(python_executable).resolve()),
        str(Path(__file__).resolve()),
        "--runtime-child",
        "--headless",
        "--treatment",
        treatment,
        "--frozen-config",
        str(Path(frozen_config_path).resolve()),
        "--out-dir",
        str(Path(treatment_dir).resolve()),
        "--run-nonce",
        run_nonce,
        "--parent-pid",
        str(parent_pid),
        "--expected-config-sha256",
        expected_config_sha256,
    ]


def select_decision(components: Mapping[str, Any]) -> str:
    expected = {
        "runtime_error",
        "protocol_no_go",
        "contact_report_perturbation",
        "original_contact_lift_passed",
        "retention_continuation_passed",
        "zero_friction_causality_passed",
    }
    if (
        not isinstance(components, Mapping)
        or set(components) != expected
        or any(type(components[name]) is not bool for name in expected)
    ):
        raise ValueError("probe_decision_components_invalid")
    if components["runtime_error"]:
        return DECISIONS[0]
    if components["protocol_no_go"]:
        return DECISIONS[1]
    if components["contact_report_perturbation"]:
        return DECISIONS[2]
    if not components["original_contact_lift_passed"]:
        return DECISIONS[3]
    if not components["retention_continuation_passed"]:
        return DECISIONS[4]
    if not components["zero_friction_causality_passed"]:
        return DECISIONS[5]
    return DECISIONS[6]


def make_trace_record(
    prior_records: Sequence[Mapping[str, Any]],
    *,
    treatment: str,
    run_nonce: str,
    parent_pid: int,
    child_pid: int,
    run_id: str,
    kind: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    if treatment not in TREATMENTS or kind not in {
        "bootstrap",
        "transition",
        "protocol_blocker",
        "terminal",
    }:
        raise ValueError("probe_trace_record_identity_invalid")
    if (
        not isinstance(run_nonce, str)
        or not run_nonce
        or not isinstance(run_id, str)
        or not run_id
        or type(parent_pid) is not int
        or parent_pid <= 0
        or type(child_pid) is not int
        or child_pid <= 0
        or not isinstance(payload, Mapping)
    ):
        raise ValueError("probe_trace_record_identity_invalid")
    previous = (
        prior_records[-1].get("record_sha256") if prior_records else _ZERO_SHA256
    )
    if not _is_sha256(previous):
        raise ValueError("probe_trace_previous_hash_invalid")
    record = {
        "schema_version": 1,
        "manifest_type": TRACE_MANIFEST_TYPE,
        "record_index": len(prior_records),
        "treatment": treatment,
        "run_nonce": run_nonce,
        "parent_pid": parent_pid,
        "child_pid": child_pid,
        "run_id": run_id,
        "kind": kind,
        "previous_sha256": previous,
        "payload": copy.deepcopy(dict(payload)),
    }
    return {**record, "record_sha256": _canonical_json_sha256(record)}


def validate_trace_records(
    records: Sequence[Mapping[str, Any]],
    *,
    expected_treatment: str,
    expected_run_nonce: str,
    expected_parent_pid: int,
    expected_child_pid: int,
    expected_run_id: str,
) -> dict[str, Any]:
    if (
        isinstance(records, (str, bytes, bytearray))
        or not isinstance(records, Sequence)
        or not records
    ):
        raise ValueError("probe_trace_records_invalid")
    previous = _ZERO_SHA256
    terminal_index = None
    for index, raw in enumerate(records):
        if terminal_index is not None:
            raise ValueError("probe_trace_data_after_terminal")
        if not isinstance(raw, Mapping):
            raise ValueError("probe_trace_record_invalid")
        record = dict(raw)
        digest = record.pop("record_sha256", None)
        if (
            record.get("schema_version") != 1
            or record.get("manifest_type") != TRACE_MANIFEST_TYPE
            or record.get("record_index") != index
            or record.get("treatment") != expected_treatment
            or record.get("run_nonce") != expected_run_nonce
            or record.get("parent_pid") != expected_parent_pid
            or record.get("child_pid") != expected_child_pid
            or record.get("run_id") != expected_run_id
            or record.get("previous_sha256") != previous
            or record.get("kind")
            not in {"bootstrap", "transition", "protocol_blocker", "terminal"}
            or not isinstance(record.get("payload"), Mapping)
        ):
            raise ValueError("probe_trace_record_identity_invalid")
        if digest != _canonical_json_sha256(record):
            raise ValueError("probe_trace_record_hash_mismatch")
        previous = digest
        if record["kind"] == "terminal":
            terminal_index = index
    if terminal_index is None:
        raise ValueError("probe_trace_terminal_missing")
    return {
        "record_count": len(records),
        "terminal_index": terminal_index,
        "chain_sha256": previous,
        "valid": True,
    }


def _action_channel_value(action: Any, name: str) -> Any:
    if isinstance(action, Mapping):
        return action.get(name)
    return getattr(action, name, None)


def canonicalize_action(action: Any) -> dict[str, Any]:
    if action is None:
        raise ValueError("probe_action_required")
    channels: dict[str, Any] = {}
    for name in ACTION_CHANNELS:
        value = _action_channel_value(action, name)
        if value is None:
            channels[name] = {
                "present": False,
                "shape": None,
                "none_mask_hex": None,
                "float64_le_hex": None,
            }
            continue
        if isinstance(value, (str, bytes, bytearray)):
            raise ValueError("probe_action_value_invalid")
        try:
            sequence = list(value)
        except TypeError as exc:
            raise ValueError("probe_action_value_invalid") from exc
        numeric = np.zeros(len(sequence), dtype=np.dtype("<f8"))
        mask = bytearray((len(sequence) + 7) // 8)
        for index, item in enumerate(sequence):
            if item is None:
                mask[index // 8] |= 1 << (index % 8)
                continue
            if (
                isinstance(item, bool)
                or not isinstance(item, (int, float, np.number))
                or not math.isfinite(float(item))
            ):
                raise ValueError("probe_action_value_invalid")
            numeric[index] = float(item)
        numeric[numeric == 0.0] = 0.0
        channels[name] = {
            "present": True,
            "shape": [len(sequence)],
            "none_mask_hex": bytes(mask).hex(),
            "float64_le_hex": numeric.tobytes(order="C").hex(),
        }
    payload = {"channel_order": list(ACTION_CHANNELS), "channels": channels}
    return {**payload, "sha256": _canonical_json_sha256(payload)}


def raw_action_channels(action: Any) -> dict[str, Any]:
    result = {}
    for name in ACTION_CHANNELS:
        value = _action_channel_value(action, name)
        if value is None:
            result[name] = None
            continue
        try:
            sequence = list(value)
        except TypeError as exc:
            raise ValueError("probe_action_value_invalid") from exc
        native = []
        for item in sequence:
            if item is None:
                native.append(None)
            elif (
                isinstance(item, (int, float, np.number))
                and not isinstance(item, bool)
                and math.isfinite(float(item))
            ):
                native.append(float(item))
            else:
                raise ValueError("probe_action_value_invalid")
        result[name] = native
    return result


def validate_action_ledger(
    records: Sequence[Mapping[str, Any]], *, maximum_production_steps: int
) -> dict[str, Any]:
    if (
        type(maximum_production_steps) is not int
        or maximum_production_steps <= 0
        or isinstance(records, (str, bytes, bytearray))
        or not isinstance(records, Sequence)
        or not records
        or len(records) > maximum_production_steps
    ):
        raise ValueError("probe_ledger_records_invalid")
    close_index = None
    lift_index = None
    k_lift = None
    apply_indices = []
    terminal_outcomes = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping) or record.get("transition_index") != index:
            raise ValueError("probe_ledger_transition_index_invalid")
        state_present = record.get("state_present")
        calls = record.get("controller_call_count")
        action = record.get("action")
        applies = record.get("apply_count")
        if type(state_present) is not bool or type(calls) is not int or type(applies) is not int:
            raise ValueError("probe_ledger_record_invalid")
        if not state_present:
            if calls != 0:
                raise ValueError("probe_ledger_controller_called_on_none")
            if action is not None or applies != 0:
                raise ValueError("probe_ledger_none_state_action_invalid")
        elif calls != 1:
            raise ValueError("probe_ledger_controller_call_count_invalid")
        if action is None:
            if applies != 0 or record.get("integrating_transition_index") is not None:
                raise ValueError("probe_ledger_apply_count_invalid")
        else:
            if (
                not isinstance(action, Mapping)
                or not _is_sha256(action.get("sha256"))
                or applies != 1
                or record.get("integrating_transition_index") != index + 1
            ):
                raise ValueError("probe_ledger_apply_count_invalid")
            apply_index = record.get("apply_index")
            if type(apply_index) is not int or apply_index < 0:
                raise ValueError("probe_ledger_apply_index_invalid")
            apply_indices.append(apply_index)
        event = record.get("native_event")
        if event is not None and (type(event) is not int or not 0 <= event <= 6):
            raise ValueError("probe_ledger_native_event_invalid")
        if event == 4 and action is not None and close_index is None:
            close_index = index
        if event == 5 and action is not None and lift_index is None:
            lift_index = index
            k_lift = index + 1
        outcome = record.get("terminal_outcome")
        if outcome is not None:
            if outcome not in {"POURING", "PICKING_FAILURE"}:
                raise ValueError("probe_ledger_terminal_outcome_invalid")
            terminal_outcomes.append((index, outcome))
    if apply_indices != list(range(len(apply_indices))):
        raise ValueError("probe_ledger_apply_index_invalid")
    if (
        close_index is None
        or lift_index is None
        or close_index >= lift_index
        or len(terminal_outcomes) != 1
    ):
        raise ValueError("probe_ledger_native_sequence_invalid")
    return {
        "valid": True,
        "record_count": len(records),
        "close_transition_index": close_index,
        "lift_command_transition_index": lift_index,
        "k_lift": k_lift,
        "apply_count": len(apply_indices),
        "terminal_transition_index": terminal_outcomes[0][0],
        "terminal_outcome": terminal_outcomes[0][1],
    }


def _finite_vector(value: Any, *, field: str, unit: bool = False) -> np.ndarray:
    try:
        vector = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"probe_{field}_invalid") from exc
    if vector.shape != (3,) or not np.isfinite(vector).all():
        raise ValueError(f"probe_{field}_invalid")
    if unit:
        norm = float(np.linalg.norm(vector))
        if norm <= 1.0e-12:
            raise ValueError(f"probe_{field}_invalid")
        vector = vector / norm
    vector[vector == 0.0] = 0.0
    return vector


def _occurrence_pair(occurrence: Mapping[str, Any]) -> tuple[str, str]:
    pair = occurrence.get("canonical_pair")
    if (
        not isinstance(pair, Sequence)
        or isinstance(pair, (str, bytes, bytearray))
        or len(pair) != 2
    ):
        raise ValueError("probe_contact_pair_invalid")
    paths = []
    for item in pair:
        if (
            not isinstance(item, Mapping)
            or not isinstance(item.get("collider_path"), str)
            or not item["collider_path"]
        ):
            raise ValueError("probe_contact_pair_invalid")
        if item.get("proto_index") != _PROTO_NONE:
            raise ValueError("probe_contact_prototype_unsupported")
        paths.append(item["collider_path"])
    if paths[0] == paths[1]:
        raise ValueError("probe_contact_pair_invalid")
    return paths[0], paths[1]


def reduce_contact_occurrence(
    occurrence: Mapping[str, Any],
    *,
    source_collider: str,
    impulse_actor: str,
    normal_direction: str,
) -> dict[str, Any]:
    if not isinstance(occurrence, Mapping):
        raise TypeError("probe_contact_occurrence_mapping_required")
    pair = _occurrence_pair(occurrence)
    if source_collider not in pair:
        raise ValueError("probe_contact_source_not_in_pair")
    if impulse_actor not in {"collider0", "collider1"}:
        raise ValueError("probe_contact_impulse_actor_invalid")
    if normal_direction not in {
        "collider0_to_collider1",
        "collider1_to_collider0",
    }:
        raise ValueError("probe_contact_normal_direction_invalid")
    fragments = occurrence.get("fragments")
    if (
        not isinstance(fragments, Sequence)
        or isinstance(fragments, (str, bytes, bytearray))
        or not fragments
    ):
        raise ValueError("probe_contact_fragments_invalid")
    points = []
    anchors = []
    normal_sum = np.float64(0.0)
    friction_norm = np.float64(0.0)
    for fragment in fragments:
        if not isinstance(fragment, Mapping) or not isinstance(
            fragment.get("header"), Mapping
        ):
            raise ValueError("probe_contact_fragment_invalid")
        header = fragment["header"]
        collider0 = header.get("collider0")
        collider1 = header.get("collider1")
        if {collider0, collider1} != set(pair) or collider0 == collider1:
            raise ValueError("probe_contact_fragment_pair_mismatch")
        source_index = 0 if collider0 == source_collider else 1
        raw_impulse_index = 0 if impulse_actor == "collider0" else 1
        impulse_sign = 1.0 if raw_impulse_index == source_index else -1.0
        raw_normal_from = 0 if normal_direction == "collider0_to_collider1" else 1
        normal_sign = -1.0 if raw_normal_from == source_index else 1.0
        contact_data = fragment.get("contact_data")
        friction_data = fragment.get("friction_anchors")
        if (
            not isinstance(contact_data, Sequence)
            or isinstance(contact_data, (str, bytes, bytearray))
            or not isinstance(friction_data, Sequence)
            or isinstance(friction_data, (str, bytes, bytearray))
        ):
            raise ValueError("probe_contact_fragment_records_invalid")
        for point in contact_data:
            if not isinstance(point, Mapping):
                raise ValueError("probe_contact_point_invalid")
            position = _finite_vector(point.get("position"), field="contact_position")
            normal = (
                _finite_vector(point.get("normal"), field="contact_normal", unit=True)
                * normal_sign
            )
            impulse = (
                _finite_vector(point.get("impulse"), field="contact_impulse")
                * impulse_sign
            )
            separation = point.get("separation")
            if (
                isinstance(separation, bool)
                or not isinstance(separation, (int, float, np.number))
                or not math.isfinite(float(separation))
            ):
                raise ValueError("probe_contact_separation_invalid")
            projected = float(impulse @ normal)
            if projected < 0.0:
                raise ValueError("probe_contact_negative_normal_impulse")
            normal_sum = np.float64(normal_sum + np.float64(projected))
            points.append(
                {
                    "position_world_m": position.tolist(),
                    "source_normal_world": normal.tolist(),
                    "source_impulse_n_s": impulse.tolist(),
                    "normal_impulse_n_s": projected,
                    "separation_m": float(separation),
                }
            )
        for anchor in friction_data:
            if not isinstance(anchor, Mapping):
                raise ValueError("probe_contact_friction_anchor_invalid")
            position = _finite_vector(
                anchor.get("position"), field="contact_friction_position"
            )
            impulse = (
                _finite_vector(
                    anchor.get("impulse"), field="contact_friction_impulse"
                )
                * impulse_sign
            )
            norm = float(np.linalg.norm(impulse))
            friction_norm = np.float64(friction_norm + np.float64(norm))
            anchors.append(
                {
                    "position_world_m": position.tolist(),
                    "source_impulse_n_s": impulse.tolist(),
                    "impulse_norm_n_s": norm,
                }
            )
    return {
        "source_collider": source_collider,
        "other_collider": pair[0] if pair[1] == source_collider else pair[1],
        "current": occurrence.get("current") is True,
        "event_sequence": occurrence.get("event_sequence"),
        "points": points,
        "friction_anchors": anchors,
        "normal_impulse_n_s": float(normal_sum),
        "friction_anchor_norm_n_s": float(friction_norm),
        "fragment_count": len(fragments),
    }


def _bound_authority(bound: Mapping[str, Any]) -> tuple[np.ndarray, ...]:
    if not isinstance(bound, Mapping) or not isinstance(bound.get("path"), str):
        raise ValueError("probe_bound_invalid")
    low = _finite_vector(bound.get("range_min_m"), field="bound_range")
    high = _finite_vector(bound.get("range_max_m"), field="bound_range")
    if np.any(high <= low):
        raise ValueError("probe_bound_degenerate")
    try:
        bbox = np.asarray(bound.get("bbox_matrix"), dtype=np.float64)
        parent = np.asarray(bound.get("parent_world_matrix"), dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("probe_bound_matrix_invalid") from exc
    if (
        bbox.shape != (4, 4)
        or parent.shape != (4, 4)
        or not np.isfinite(bbox).all()
        or not np.isfinite(parent).all()
        or abs(float(np.linalg.det(bbox))) <= 1.0e-15
        or abs(float(np.linalg.det(parent))) <= 1.0e-15
    ):
        raise ValueError("probe_bound_matrix_invalid")
    raw = np.asarray(
        [
            [x, y, z, 1.0]
            for x in (low[0], high[0])
            for y in (low[1], high[1])
            for z in (low[2], high[2])
        ],
        dtype=np.float64,
    )
    return low, high, bbox, parent, raw


def transform_sealed_bound(bound: Mapping[str, Any]) -> dict[str, Any]:
    low, high, bbox, parent, raw = _bound_authority(bound)
    parent_corners = raw @ bbox
    world = parent_corners @ parent
    if not np.isfinite(world).all() or not np.allclose(
        world[:, 3], 1.0, rtol=0.0, atol=1.0e-12
    ):
        raise ValueError("probe_bound_transform_invalid")
    center = np.mean(world[:, :3], axis=0)
    return {
        "path": bound["path"],
        "range_min_m": low.tolist(),
        "range_max_m": high.tolist(),
        "raw_corners_m": raw[:, :3].tolist(),
        "parent_corners_m": parent_corners[:, :3].tolist(),
        "world_corners_m": world[:, :3].tolist(),
        "world_center_m": center.tolist(),
        "authority_sha256": _canonical_json_sha256(
            {
                "range_min_m": low.tolist(),
                "range_max_m": high.tolist(),
                "bbox_matrix": bbox.tolist(),
                "parent_world_matrix": parent.tolist(),
                "world_corners_m": world[:, :3].tolist(),
            }
        ),
    }


def world_point_to_raw_bound(
    point_world_m: Any, bound: Mapping[str, Any]
) -> list[float]:
    point = _finite_vector(point_world_m, field="bound_world_point")
    _low, _high, bbox, parent, _raw = _bound_authority(bound)
    homogeneous = np.append(point, 1.0)
    raw = homogeneous @ np.linalg.inv(parent) @ np.linalg.inv(bbox)
    if not np.isfinite(raw).all() or not math.isclose(
        float(raw[3]), 1.0, rel_tol=0.0, abs_tol=1.0e-10
    ):
        raise ValueError("probe_bound_inverse_transform_invalid")
    return raw[:3].tolist()


def _normal_to_world(local_normal: np.ndarray, bound: Mapping[str, Any]) -> np.ndarray:
    _low, _high, bbox, parent, _raw = _bound_authority(bound)
    linear = (bbox @ parent)[:3, :3]
    world = local_normal @ np.linalg.inv(linear)
    norm = float(np.linalg.norm(world))
    if not math.isfinite(norm) or norm <= 1.0e-12:
        raise ValueError("probe_bound_normal_transform_invalid")
    return world / norm


def _vessel_axis(
    source_bound: Mapping[str, Any], gravity_world_m_s2: Any
) -> tuple[np.ndarray, int, int, float]:
    gravity = _finite_vector(gravity_world_m_s2, field="gravity")
    magnitude = float(np.linalg.norm(gravity))
    if magnitude <= 1.0e-12:
        raise ValueError("probe_gravity_invalid")
    anti_gravity = -gravity / magnitude
    candidates = []
    for axis_index in range(3):
        for sign in (-1, 1):
            local = np.zeros(3, dtype=np.float64)
            local[axis_index] = sign
            world = _normal_to_world(local, source_bound)
            candidates.append((float(world @ anti_gravity), axis_index, sign, world))
    cosine, axis_index, sign, world = max(candidates, key=lambda item: item[0])
    if cosine < 0.95:
        raise ValueError("probe_vessel_axis_alignment_invalid")
    return world, axis_index, sign, cosine


def evaluate_bilateral_geometry(
    occurrences: Sequence[Mapping[str, Any]],
    *,
    geometry: Mapping[str, Any],
    finger_aperture_rate_m_s: float,
) -> dict[str, Any]:
    protocol_failures: list[str] = []
    failures: list[str] = []
    output_points: list[dict[str, Any]] = []
    try:
        if (
            isinstance(finger_aperture_rate_m_s, bool)
            or not isinstance(
                finger_aperture_rate_m_s, (int, float, np.number)
            )
            or not math.isfinite(float(finger_aperture_rate_m_s))
        ):
            raise ValueError("probe_aperture_rate_invalid")
        source_bound = geometry.get("source")
        finger_bounds = geometry.get("finger_colliders")
        targets = geometry.get("target_pairs")
        if (
            not isinstance(source_bound, Mapping)
            or not isinstance(finger_bounds, Mapping)
            or not isinstance(targets, Sequence)
            or isinstance(targets, (str, bytes, bytearray))
        ):
            raise ValueError("probe_geometry_authority_invalid")
        source = transform_sealed_bound(source_bound)
        source_corners = np.asarray(source["world_corners_m"], dtype=np.float64)
        up, _axis_index, _axis_sign, axis_cosine = _vessel_axis(
            source_bound, geometry.get("gravity_world_m_s2")
        )
        heights = source_corners @ up
        height_min = float(np.min(heights))
        height_max = float(np.max(heights))
        if height_max <= height_min:
            raise ValueError("probe_source_height_degenerate")
        source_center = np.mean(source_corners, axis=0)
        target_by_pair = {}
        colliders_by_side: dict[str, list[str]] = {"left": [], "right": []}
        for target in targets:
            if not isinstance(target, Mapping) or target.get("side") not in {
                "left",
                "right",
            }:
                raise ValueError("probe_target_pair_set_invalid")
            source_path = target.get("source_collider")
            finger_path = target.get("finger_collider")
            if (
                source_path != source_bound.get("path")
                or finger_path not in finger_bounds
                or not isinstance(target.get("finger_body"), str)
            ):
                raise ValueError("probe_target_pair_set_invalid")
            key = frozenset((source_path, finger_path))
            if key in target_by_pair:
                raise ValueError("probe_target_pair_set_invalid")
            target_by_pair[key] = dict(target)
            colliders_by_side[target["side"]].append(finger_path)
        if not all(colliders_by_side.values()):
            raise ValueError("probe_target_pair_side_missing")

        transformed_fingers = {
            path: transform_sealed_bound(bound)
            for path, bound in finger_bounds.items()
        }
        side_centers = {}
        for side, paths in colliders_by_side.items():
            corners = np.concatenate(
                [
                    np.asarray(
                        transformed_fingers[path]["world_corners_m"],
                        dtype=np.float64,
                    )
                    for path in paths
                ],
                axis=0,
            )
            low = corners.min(axis=0)
            high = corners.max(axis=0)
            if np.any(high <= low):
                raise ValueError("probe_finger_side_bound_degenerate")
            side_centers[side] = (low + high) / 2.0
        closing = side_centers["right"] - side_centers["left"]
        closing = closing - up * float(closing @ up)
        closing_norm = float(np.linalg.norm(closing))
        if closing_norm <= 1.0e-12:
            raise ValueError("probe_closing_axis_degenerate")
        closing = closing / closing_norm
        source_coordinates = source_corners @ closing
        source_coordinate = float((source_coordinates.min() + source_coordinates.max()) / 2.0)
        source_half_width = float(
            (source_coordinates.max() - source_coordinates.min()) / 2.0
        )
        if source_half_width <= 0.0:
            raise ValueError("probe_source_half_width_degenerate")

        current_by_side: dict[str, list[Mapping[str, Any]]] = {
            "left": [],
            "right": [],
        }
        for occurrence in occurrences:
            if not isinstance(occurrence, Mapping):
                protocol_failures.append("occurrence_not_mapping")
                continue
            key = frozenset(
                (
                    occurrence.get("source_collider"),
                    occurrence.get("finger_collider"),
                )
            )
            target = target_by_pair.get(key)
            if target is None:
                protocol_failures.append("unknown_target_pair")
                continue
            if occurrence.get("current") is not True:
                continue
            points = occurrence.get("points")
            if (
                not isinstance(points, Sequence)
                or isinstance(points, (str, bytes, bytearray))
                or not points
            ):
                protocol_failures.append("current_pair_without_points")
                continue
            current_by_side[target["side"]].append(occurrence)
            finger_path = target["finger_collider"]
            finger_bound = finger_bounds[finger_path]
            finger_center = np.asarray(
                transformed_fingers[finger_path]["world_center_m"],
                dtype=np.float64,
            )
            toward_source = source_center - finger_center
            toward_norm = float(np.linalg.norm(toward_source))
            if toward_norm <= 1.0e-12:
                raise ValueError("probe_inner_half_vector_degenerate")
            toward_source = toward_source / toward_norm
            face_candidates = []
            for axis in range(3):
                for sign in (-1, 1):
                    local_normal = np.zeros(3, dtype=np.float64)
                    local_normal[axis] = sign
                    normal = _normal_to_world(local_normal, finger_bound)
                    face_candidates.append(
                        (float(normal @ toward_source), axis, sign, normal)
                    )
            face_candidates.sort(key=lambda item: item[0], reverse=True)
            if (
                face_candidates[0][0] < 0.8
                or math.isclose(
                    face_candidates[0][0],
                    face_candidates[1][0],
                    rel_tol=0.0,
                    abs_tol=1.0e-12,
                )
            ):
                raise ValueError("probe_inner_face_ambiguous")
            face_axis = face_candidates[0][1]
            low = np.asarray(finger_bound["range_min_m"], dtype=np.float64)
            high = np.asarray(finger_bound["range_max_m"], dtype=np.float64)
            tangent_axes = [axis for axis in range(3) if axis != face_axis]
            for point_record in points:
                if not isinstance(point_record, Mapping):
                    protocol_failures.append("point_not_mapping")
                    continue
                point = _finite_vector(
                    point_record.get("position_world_m"), field="geometry_point"
                )
                normal = _finite_vector(
                    point_record.get("source_normal_world"),
                    field="geometry_normal",
                    unit=True,
                )
                raw = np.asarray(
                    world_point_to_raw_bound(point, finger_bound),
                    dtype=np.float64,
                )
                normalized_height = float((point @ up - height_min) / (height_max - height_min))
                inner_displacement = float((point - finger_center) @ toward_source)
                pad_margins = [
                    min(
                        float(raw[axis] - (low[axis] + 0.001)),
                        float((high[axis] - 0.001) - raw[axis]),
                    )
                    for axis in tangent_axes
                ]
                side = target["side"]
                coordinate = float(point @ closing)
                side_margin = (
                    source_coordinate - 0.25 * source_half_width - coordinate
                    if side == "left"
                    else coordinate - (source_coordinate + 0.25 * source_half_width)
                )
                inward = source_center - point
                inward = inward - up * float(inward @ up)
                inward_norm = float(np.linalg.norm(inward))
                if inward_norm <= 1.0e-12:
                    raise ValueError("probe_inward_normal_vector_degenerate")
                inward = inward / inward_norm
                inward_cosine = float(normal @ inward)
                vertical_cosine = abs(float(normal @ up))
                margins = {
                    "height_lower": normalized_height - 0.20,
                    "height_upper": 0.80 - normalized_height,
                    "inner_half_m": inner_displacement,
                    "pad_tangent_0_m": pad_margins[0],
                    "pad_tangent_1_m": pad_margins[1],
                    "opposite_side_m": side_margin,
                    "inward_cosine": inward_cosine - 0.8,
                    "vertical_normal_cosine": 0.25 - vertical_cosine,
                    "aperture_rate_m_s": 0.01 - float(finger_aperture_rate_m_s),
                }
                point_failures = []
                if not 0.20 <= normalized_height <= 0.80:
                    point_failures.append("height")
                if inner_displacement < 0.0:
                    point_failures.append("inner_half")
                if any(margin < 0.0 for margin in pad_margins):
                    point_failures.append("pad_interior")
                if side_margin < 0.0:
                    point_failures.append("opposite_source_side")
                if inward_cosine < 0.8:
                    point_failures.append("inward_normal")
                if vertical_cosine > 0.25:
                    point_failures.append("vertical_normal")
                failures.extend(point_failures)
                output_points.append(
                    {
                        "side": side,
                        "finger_collider": finger_path,
                        "position_world_m": point.tolist(),
                        "source_normal_world": normal.tolist(),
                        "normalized_height": normalized_height,
                        "margins": margins,
                        "failure_reasons": point_failures,
                    }
                )
        for side in ("left", "right"):
            if not current_by_side[side]:
                failures.append(f"{side}_current_contact_missing")
        left_normals = [
            np.asarray(point["source_normal_world"], dtype=np.float64)
            for point in output_points
            if point["side"] == "left"
        ]
        right_normals = [
            np.asarray(point["source_normal_world"], dtype=np.float64)
            for point in output_points
            if point["side"] == "right"
        ]
        for left in left_normals:
            for right in right_normals:
                if float(left @ right) > -0.8:
                    failures.append("opposing_normals")
        if float(finger_aperture_rate_m_s) > 0.01:
            failures.append("aperture_rate")
    except (KeyError, TypeError, ValueError, np.linalg.LinAlgError) as exc:
        protocol_failures.append(str(exc))
        axis_cosine = None
        source_half_width = None
    protocol_failures = sorted(set(protocol_failures))
    failures = sorted(set(failures))
    return {
        "protocol_valid": not protocol_failures,
        "qualified": bool(not protocol_failures and not failures),
        "protocol_failures": protocol_failures,
        "failure_reasons": failures,
        "left_point_count": sum(
            point["side"] == "left" for point in output_points
        ),
        "right_point_count": sum(
            point["side"] == "right" for point in output_points
        ),
        "points": output_points,
        "vessel_axis_antigravity_cosine": axis_cosine,
        "source_half_width_m": source_half_width,
    }


def unique_minimum_distance_assignment(
    first_points: Any,
    second_points: Any,
    *,
    maximum_distance_m: float,
) -> dict[str, Any]:
    try:
        first = np.asarray(first_points, dtype=np.float64)
        second = np.asarray(second_points, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("probe_assignment_points_invalid") from exc
    if (
        first.ndim != 2
        or second.ndim != 2
        or first.shape[1:] != (3,)
        or second.shape[1:] != (3,)
        or len(first) == 0
        or len(first) != len(second)
        or not np.isfinite(first).all()
        or not np.isfinite(second).all()
        or isinstance(maximum_distance_m, bool)
        or not isinstance(maximum_distance_m, (int, float, np.number))
        or not math.isfinite(float(maximum_distance_m))
        or float(maximum_distance_m) < 0.0
    ):
        raise ValueError("probe_assignment_points_invalid")
    distances = np.linalg.norm(first[:, None, :] - second[None, :, :], axis=2)
    if len(first) <= 8:
        candidates = []
        for permutation in itertools.permutations(range(len(first))):
            total = float(sum(distances[row, column] for row, column in enumerate(permutation)))
            candidates.append((total, permutation))
        candidates.sort(key=lambda item: item[0])
        best_total, best = candidates[0]
        if len(candidates) > 1 and math.isclose(
            best_total,
            candidates[1][0],
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise ValueError("probe_assignment_not_unique")
        assignment = list(best)
    else:
        from scipy.optimize import linear_sum_assignment

        rows, columns = linear_sum_assignment(distances)
        assignment = [0] * len(first)
        for row, column in zip(rows, columns):
            assignment[int(row)] = int(column)
        best_total = float(distances[rows, columns].sum())
        for row, column in zip(rows, columns):
            alternate = distances.copy()
            alternate[row, column] = np.inf
            alt_rows, alt_columns = linear_sum_assignment(alternate)
            alt_total = float(alternate[alt_rows, alt_columns].sum())
            if math.isclose(best_total, alt_total, rel_tol=0.0, abs_tol=1.0e-12):
                raise ValueError("probe_assignment_not_unique")
    matched = [float(distances[row, column]) for row, column in enumerate(assignment)]
    maximum = max(matched)
    if maximum > float(maximum_distance_m):
        raise ValueError("probe_assignment_distance_exceeded")
    return {
        "assignment": assignment,
        "distances_m": matched,
        "total_distance_m": float(sum(matched)),
        "maximum_distance_m": maximum,
        "unique": True,
    }


def _transition_records(
    records: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    if (
        isinstance(records, (str, bytes, bytearray))
        or not isinstance(records, Sequence)
        or not records
    ):
        raise ValueError("probe_transition_trace_invalid")
    result = []
    for index, record in enumerate(records):
        if (
            not isinstance(record, Mapping)
            or record.get("transition_index") != index
            or not isinstance(record.get("pre"), Mapping)
            or not isinstance(record.get("post"), Mapping)
            or not isinstance(record.get("contact"), Mapping)
        ):
            raise ValueError("probe_transition_trace_invalid")
        result.append(record)
    return result


def _state_com(record: Mapping[str, Any], field: str) -> np.ndarray:
    state = record.get(field)
    if not isinstance(state, Mapping):
        raise ValueError("probe_transition_state_invalid")
    return _finite_vector(state.get("source_com_m"), field="transition_com")


def _state_scalar(
    state: Mapping[str, Any], field: str, *, nonnegative: bool = True
) -> float:
    value = state.get(field)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float, np.number))
        or not math.isfinite(float(value))
        or (nonnegative and float(value) < 0.0)
    ):
        raise ValueError("probe_transition_state_invalid")
    return float(value)


def _lift_transition(records: Sequence[Mapping[str, Any]]) -> int:
    indices = []
    for record in records:
        receipt = record.get("action_receipt")
        if receipt is None:
            continue
        if not isinstance(receipt, Mapping):
            raise ValueError("probe_lift_receipt_invalid")
        if receipt.get("native_event") == 5:
            if (
                receipt.get("applied") is not True
                or receipt.get("normal_return") is not True
                or receipt.get("apply_count") != 1
            ):
                raise ValueError("probe_lift_receipt_invalid")
            indices.append(int(record["transition_index"]))
    if len(indices) != 1 or indices[0] < 1:
        raise ValueError("probe_lift_transition_invalid")
    return indices[0]


def _settled_supported_baseline(
    records: Sequence[Mapping[str, Any]], k_lift: int
) -> tuple[int, np.ndarray]:
    run = 0
    candidates = []
    prior_post = None
    for index, record in enumerate(records[:k_lift]):
        state = record["post"]
        post_com = _state_com(record, "post")
        reference = _state_com(record, "pre") if prior_post is None else prior_post
        settled = bool(
            state.get("support_current") is True
            and _state_scalar(state, "source_linear_speed_m_s") <= 0.001
            and _state_scalar(state, "source_angular_speed_degrees_s") <= 0.1
            and _state_scalar(state, "finger_aperture_rate_m_s") <= 0.01
            and float(np.linalg.norm(post_com - reference)) <= 0.0001
        )
        run = run + 1 if settled else 0
        if run >= 10:
            candidates.append((index, post_com.copy()))
        prior_post = post_com
    if not candidates:
        raise ValueError("probe_settled_supported_window_missing")
    return candidates[-1]


def _contact_gate(
    record: Mapping[str, Any], *, friction_required: bool
) -> tuple[bool, list[str]]:
    contact = record["contact"]
    failures = []
    if contact.get("bilateral_qualified") is not True:
        failures.append("bilateral_geometry")
    if contact.get("prohibited_contact") is not False:
        failures.append("prohibited_contact")
    for field, limit in (
        ("source_tool_drift_translation_m", 0.005),
        ("source_tool_drift_rotation_degrees", 5.0),
    ):
        value = contact.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float, np.number))
            or not math.isfinite(float(value))
            or float(value) > limit
        ):
            failures.append(field)
    if friction_required:
        for side in ("left", "right"):
            value = contact.get(f"{side}_friction_anchor_norm_n_s")
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float, np.number))
                or not math.isfinite(float(value))
                or float(value) <= 1.0e-5
            ):
                failures.append(f"{side}_friction_anchor_norm")
    return not failures, failures


def evaluate_original_lift_trace(
    records: Sequence[Mapping[str, Any]],
    *,
    physics_dt: float,
    retention_steps: int,
    rise_threshold_m: float,
) -> dict[str, Any]:
    protocol_failures = []
    lift_failures = []
    retention_failures = []
    k_lift = k_loss = k_rise = None
    airborne_duration = None
    boundary_pre_loss_speed = None
    boundary_post_rise_speed = None
    continuation_count = 0
    try:
        transitions = _transition_records(records)
        if (
            isinstance(physics_dt, bool)
            or not isinstance(physics_dt, (int, float, np.number))
            or not math.isfinite(float(physics_dt))
            or float(physics_dt) <= 0.0
            or type(retention_steps) is not int
            or retention_steps <= 0
            or isinstance(rise_threshold_m, bool)
            or not isinstance(rise_threshold_m, (int, float, np.number))
            or not math.isfinite(float(rise_threshold_m))
            or float(rise_threshold_m) <= 0.0
        ):
            raise ValueError("probe_original_trace_limits_invalid")
        k_lift = _lift_transition(transitions)
        settled_index, settled_com = _settled_supported_baseline(
            transitions, k_lift
        )
        rise_baseline = _state_com(transitions[k_lift], "pre")
        if float(np.linalg.norm(rise_baseline - settled_com)) > 0.002:
            lift_failures.append("pre_lift_rise")
        baseline_z = float(rise_baseline[2])
        for record in transitions[k_lift:]:
            index = int(record["transition_index"])
            post = record["post"]
            if k_loss is None and post.get("support_current") is False:
                k_loss = index
                contact = record["contact"]
                if (
                    contact.get("support_event") != "LOST"
                    or contact.get("support_contact_count") != 0
                    or contact.get("support_friction_anchor_count") != 0
                    or float(contact.get("support_impulse_n_s", math.nan)) != 0.0
                ):
                    protocol_failures.append("support_loss_contract")
            elif k_loss is not None and index > k_loss:
                if (
                    post.get("support_current") is not False
                    or record["contact"].get("support_event") is not None
                    or record["contact"].get("support_contact_count") != 0
                    or record["contact"].get(
                        "support_friction_anchor_count"
                    )
                    != 0
                    or float(
                        record["contact"].get(
                            "support_impulse_n_s", math.nan
                        )
                    )
                    != 0.0
                ):
                    lift_failures.append("support_recontact_after_loss")
            rise = float(_state_com(record, "post")[2] - baseline_z)
            if k_rise is None and rise >= float(rise_threshold_m):
                k_rise = index
        terminal = [
            record for record in transitions if record.get("production_terminal") is True
        ]
        if len(terminal) != 1 or terminal[0].get("terminal_outcome") not in {
            "POURING",
            "PICKING_FAILURE",
        }:
            raise ValueError("probe_production_terminal_invalid")
        terminal_record = terminal[0]
        terminal_index = int(terminal_record["transition_index"])
        if terminal_record.get("terminal_outcome") != "POURING":
            lift_failures.append("clean_original_pick_failure")
        if k_loss is None:
            lift_failures.append("support_not_lost")
        if k_rise is None:
            lift_failures.append("rise_threshold_not_crossed")
        if k_loss is not None and k_loss < k_lift:
            protocol_failures.append("support_loss_before_lift")
        if k_rise is not None and k_loss is not None:
            if k_rise < k_loss:
                protocol_failures.append("rise_before_support_loss")
            else:
                airborne_duration = (
                    k_rise - k_loss + 1
                ) * float(physics_dt)
                for record in transitions[k_loss : k_rise + 1]:
                    passed, failures = _contact_gate(
                        record, friction_required=True
                    )
                    if not passed:
                        lift_failures.extend(failures)
                boundary_pre_loss_speed = _state_scalar(
                    transitions[k_loss]["pre"],
                    "source_linear_speed_m_s",
                )
                boundary_post_rise_speed = _state_scalar(
                    transitions[k_rise]["post"],
                    "source_linear_speed_m_s",
                )
        for record in transitions[k_lift : terminal_index + 1]:
            passed, failures = _contact_gate(record, friction_required=False)
            if not passed:
                lift_failures.extend(failures)
        continuation = [
            record
            for record in transitions
            if record.get("continuation_index") is not None
        ]
        continuation_count = len(continuation)
        if [record.get("continuation_index") for record in continuation] != list(
            range(retention_steps)
        ):
            retention_failures.append("continuation_schedule")
        for record in continuation:
            if (
                record.get("controller_called") is not False
                or record.get("new_action_applied") is not False
            ):
                protocol_failures.append("continuation_new_action")
            passed, failures = _contact_gate(record, friction_required=True)
            if not passed:
                retention_failures.extend(failures)
        if continuation:
            final = continuation[-1]["post"]
            if _state_scalar(final, "source_linear_speed_m_s") > 0.02:
                retention_failures.append("terminal_linear_speed")
            if _state_scalar(final, "source_angular_speed_degrees_s") > 5.0:
                retention_failures.append("terminal_angular_speed")
        else:
            retention_failures.append("continuation_missing")
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        protocol_failures.append(str(exc))
        settled_index = None
    protocol_failures = sorted(set(protocol_failures))
    lift_failures = sorted(set(lift_failures))
    retention_failures = sorted(set(retention_failures))
    return {
        "protocol_valid": not protocol_failures,
        "protocol_failures": protocol_failures,
        "k_lift": k_lift,
        "k_loss": k_loss,
        "k_rise": k_rise,
        "final_settled_supported_transition": settled_index,
        "airborne_duration_s": airborne_duration,
        "boundary_linear_speed_pre_loss_m_s": boundary_pre_loss_speed,
        "boundary_linear_speed_post_rise_m_s": boundary_post_rise_speed,
        "contact_lift_passed": bool(not protocol_failures and not lift_failures),
        "contact_lift_failures": lift_failures,
        "retention_passed": bool(
            not protocol_failures
            and not lift_failures
            and not retention_failures
        ),
        "retention_failures": retention_failures,
        "continuation_count": continuation_count,
    }


def evaluate_zero_friction_trace(
    records: Sequence[Mapping[str, Any]],
    *,
    retention_steps: int,
    rise_threshold_m: float,
    maximum_rise_m: float,
    maximum_friction_anchor_norm_n_s: float,
) -> dict[str, Any]:
    protocol_failures = []
    causal_failures = []
    k_lift = None
    maximum_rise = None
    threshold_crossed = False
    airborne_retention = False
    try:
        transitions = _transition_records(records)
        for name, value in (
            ("rise_threshold", rise_threshold_m),
            ("maximum_rise", maximum_rise_m),
            ("maximum_friction", maximum_friction_anchor_norm_n_s),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float, np.number))
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise ValueError(f"probe_ablation_{name}_invalid")
        if type(retention_steps) is not int or retention_steps <= 0:
            raise ValueError("probe_ablation_retention_steps_invalid")
        k_lift = _lift_transition(transitions)
        baseline_z = float(_state_com(transitions[k_lift], "pre")[2])
        terminal = [
            record for record in transitions if record.get("production_terminal") is True
        ]
        if len(terminal) != 1 or terminal[0].get("terminal_outcome") not in {
            "POURING",
            "PICKING_FAILURE",
        }:
            raise ValueError("probe_ablation_terminal_invalid")
        continuation = [
            record
            for record in transitions
            if record.get("continuation_index") is not None
        ]
        if [record.get("continuation_index") for record in continuation] != list(
            range(retention_steps)
        ):
            causal_failures.append("continuation_schedule")
        if any(
            record.get("controller_called") is not False
            or record.get("new_action_applied") is not False
            for record in continuation
        ):
            protocol_failures.append("ablation_continuation_new_action")
        relevant = transitions[k_lift:]
        rises = [
            float(_state_com(record, "post")[2] - baseline_z)
            for record in relevant
        ]
        maximum_rise = max(rises, default=0.0)
        threshold_crossed = any(
            rise >= float(rise_threshold_m) for rise in rises
        )
        unsupported_run = 0
        for record in relevant:
            unsupported_run = (
                unsupported_run + 1
                if record["post"].get("support_current") is False
                else 0
            )
            airborne_retention = bool(
                airborne_retention or unsupported_run >= retention_steps
            )
            contact = record["contact"]
            if contact.get("prohibited_contact") is not False:
                protocol_failures.append("ablation_prohibited_contact")
            for side in ("left", "right"):
                value = contact.get(f"{side}_friction_anchor_norm_n_s")
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float, np.number))
                    or not math.isfinite(float(value))
                ):
                    protocol_failures.append("ablation_friction_authority")
                elif float(value) > float(maximum_friction_anchor_norm_n_s):
                    causal_failures.append(f"{side}_friction_not_zero")
        if maximum_rise >= float(maximum_rise_m):
            causal_failures.append("maximum_rise")
        if threshold_crossed:
            causal_failures.append("rise_threshold_crossed")
        if airborne_retention:
            causal_failures.append("airborne_retention")
        if terminal[0].get("terminal_outcome") == "POURING":
            causal_failures.append("ablation_transitioned_to_pouring")
        if continuation:
            final = continuation[-1]["post"]
            if _state_scalar(final, "source_linear_speed_m_s") > 0.02:
                causal_failures.append("terminal_linear_speed")
            if _state_scalar(final, "source_angular_speed_degrees_s") > 5.0:
                causal_failures.append("terminal_angular_speed")
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        protocol_failures.append(str(exc))
    protocol_failures = sorted(set(protocol_failures))
    causal_failures = sorted(set(causal_failures))
    return {
        "protocol_valid": not protocol_failures,
        "protocol_failures": protocol_failures,
        "k_lift": k_lift,
        "maximum_post_lift_rise_m": maximum_rise,
        "threshold_crossed": threshold_crossed,
        "airborne_retention": airborne_retention,
        "causal_negative_passed": bool(
            not protocol_failures and not causal_failures
        ),
        "causal_failures": causal_failures,
    }


def _quaternion_angle_degrees(first: Any, second: Any) -> float:
    try:
        one = np.asarray(first, dtype=np.float64)
        two = np.asarray(second, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("probe_quaternion_invalid") from exc
    if (
        one.shape != (4,)
        or two.shape != (4,)
        or not np.isfinite(one).all()
        or not np.isfinite(two).all()
        or float(np.linalg.norm(one)) <= 1.0e-12
        or float(np.linalg.norm(two)) <= 1.0e-12
    ):
        raise ValueError("probe_quaternion_invalid")
    dot = float(
        np.clip(abs((one / np.linalg.norm(one)) @ (two / np.linalg.norm(two))), 0.0, 1.0)
    )
    return math.degrees(2.0 * math.acos(dot))


def _compare_state_sample(
    first: Mapping[str, Any], second: Mapping[str, Any]
) -> list[str]:
    failures = []
    if first.get("controller_event") != second.get("controller_event"):
        failures.append("controller_event")
    vector_limits = {
        "joint_positions_rad": 1.0e-6,
        "tool_position_m": 1.0e-4,
        "source_position_m": 1.0e-4,
        "tool_linear_velocity_m_s": 1.0e-3,
        "source_linear_velocity_m_s": 1.0e-3,
        "tool_angular_velocity_rad_s": math.radians(0.1),
        "source_angular_velocity_rad_s": math.radians(0.1),
    }
    for field, limit in vector_limits.items():
        try:
            one = np.asarray(first.get(field), dtype=np.float64)
            two = np.asarray(second.get(field), dtype=np.float64)
            if (
                one.shape != two.shape
                or one.ndim != 1
                or not np.isfinite(one).all()
                or not np.isfinite(two).all()
                or float(np.linalg.norm(one - two)) > limit
            ):
                failures.append("state")
        except (TypeError, ValueError):
            failures.append("state_authority")
    for field in ("tool_orientation_wxyz", "source_orientation_wxyz"):
        try:
            if _quaternion_angle_degrees(first.get(field), second.get(field)) > 0.1:
                failures.append("state")
        except ValueError:
            failures.append("state_authority")
    first_margins = first.get("predicate_margins")
    second_margins = second.get("predicate_margins")
    if not isinstance(first_margins, Mapping) or not isinstance(
        second_margins, Mapping
    ):
        failures.append("predicate_margin")
    else:
        for name in sorted(set(first_margins) & set(second_margins)):
            one = first_margins[name]
            two = second_margins[name]
            if (
                isinstance(one, bool)
                or isinstance(two, bool)
                or not isinstance(one, (int, float, np.number))
                or not isinstance(two, (int, float, np.number))
                or not math.isfinite(float(one))
                or not math.isfinite(float(two))
                or float(one) == 0.0
                or float(two) == 0.0
                or math.copysign(1.0, float(one))
                != math.copysign(1.0, float(two))
                or abs(float(one) - float(two))
                > 0.5 * min(abs(float(one)), abs(float(two)))
            ):
                failures.append("predicate_margin")
                break
    return failures


def compare_control_and_instrumented(
    control: Mapping[str, Any], instrumented: Mapping[str, Any]
) -> dict[str, Any]:
    failures = []
    try:
        if not isinstance(control, Mapping) or not isinstance(instrumented, Mapping):
            raise ValueError("probe_comparison_mapping_required")
        for field in (
            "config_sha256",
            "requested_pose_sha256",
            "readback_pose_sha256",
            "reset_count",
            "controller_events",
            "action_sha256",
            "controller_outcome",
            "continuation_world_indices",
            "retention_passed",
            "common_contact_stream",
        ):
            if control.get(field) != instrumented.get(field):
                failures.append(field)
        first_samples = control.get("samples")
        second_samples = instrumented.get("samples")
        if (
            not isinstance(first_samples, Sequence)
            or not isinstance(second_samples, Sequence)
            or isinstance(first_samples, (str, bytes, bytearray))
            or isinstance(second_samples, (str, bytes, bytearray))
            or len(first_samples) != len(second_samples)
        ):
            failures.append("sample_schedule")
        else:
            for first, second in zip(first_samples, second_samples):
                failures.extend(_compare_state_sample(first, second))
        first_continuation = control.get("continuation")
        second_continuation = instrumented.get("continuation")
        if (
            not isinstance(first_continuation, Sequence)
            or not isinstance(second_continuation, Sequence)
            or len(first_continuation) != 60
            or len(second_continuation) != 60
        ):
            failures.append("continuation_schedule")
        else:
            for first, second in zip(first_continuation, second_continuation):
                sample_failures = _compare_state_sample(first, second)
                if any(
                    failure in {"state", "state_authority"}
                    for failure in sample_failures
                ):
                    failures.append("continuation_state")
                failures.extend(
                    failure
                    for failure in sample_failures
                    if failure not in {"state", "state_authority"}
                )
    except (TypeError, ValueError) as exc:
        failures.append(str(exc))
    failures = sorted(set(failures))
    return {
        "comparable": not any(
            failure.endswith("authority") or failure == "sample_schedule"
            for failure in failures
        ),
        "perturbation_detected": bool(failures),
        "failure_reasons": failures,
    }


def combine_solver_term(
    value0: float,
    value1: float,
    *,
    mode0: str,
    mode1: str,
    combine_priority: Sequence[str],
) -> dict[str, Any]:
    modes = ("average", "min", "multiply", "max")
    if (
        tuple(combine_priority) != modes
        or mode0 not in modes
        or mode1 not in modes
        or isinstance(value0, bool)
        or isinstance(value1, bool)
        or not isinstance(value0, (int, float, np.number))
        or not isinstance(value1, (int, float, np.number))
        or not math.isfinite(float(value0))
        or not math.isfinite(float(value1))
    ):
        raise ValueError("probe_material_combine_invalid")
    selected = mode0 if modes.index(mode0) >= modes.index(mode1) else mode1
    one = float(value0)
    two = float(value1)
    value = {
        "average": (one + two) / 2.0,
        "min": min(one, two),
        "multiply": one * two,
        "max": max(one, two),
    }[selected]
    canonical = np.asarray([value], dtype=np.dtype("<f4"))
    if canonical[0] == 0.0:
        canonical[0] = 0.0
    return {
        "selected_mode": selected,
        "value": value,
        "float32_hex": canonical.tobytes().hex(),
    }


def _positive_zero(value: Any) -> bool:
    return bool(
        isinstance(value, (int, float, np.number))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) == 0.0
        and math.copysign(1.0, float(value)) > 0.0
    )


def evaluate_ablation_pair_table(
    original_rows: Sequence[Mapping[str, Any]],
    ablation_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    protocol_failures = []
    target_count = 0
    try:
        if (
            isinstance(original_rows, (str, bytes, bytearray))
            or isinstance(ablation_rows, (str, bytes, bytearray))
            or not isinstance(original_rows, Sequence)
            or not isinstance(ablation_rows, Sequence)
        ):
            raise ValueError("probe_pair_table_invalid")
        original = {
            row.get("pair_id"): dict(row)
            for row in original_rows
            if isinstance(row, Mapping)
        }
        ablation = {
            row.get("pair_id"): dict(row)
            for row in ablation_rows
            if isinstance(row, Mapping)
        }
        if (
            len(original) != len(original_rows)
            or len(ablation) != len(ablation_rows)
            or set(original) != set(ablation)
            or None in original
        ):
            raise ValueError("probe_pair_table_identity_invalid")
        for pair_id in sorted(original):
            before = original[pair_id]
            after = ablation[pair_id]
            if (
                before.get("runtime_authority")
                != "physx_live_solver_material_v1"
                or after.get("runtime_authority")
                != "physx_live_solver_material_v1"
            ):
                protocol_failures.append("live_material_authority_missing")
            if before.get("eligible") is not True or after.get("eligible") is not True:
                protocol_failures.append("pair_eligibility_invalid")
            if before.get("target_pair") != after.get("target_pair"):
                protocol_failures.append("target_pair_identity_changed")
                continue
            if before.get("target_pair") is True:
                target_count += 1
                excluded = {
                    "effective_static_friction",
                    "effective_dynamic_friction",
                }
                if {
                    key: value for key, value in before.items() if key not in excluded
                } != {
                    key: value for key, value in after.items() if key not in excluded
                }:
                    protocol_failures.append("target_nonfriction_term_changed")
                for field in excluded:
                    original_value = before.get(field)
                    ablated_value = after.get(field)
                    if (
                        isinstance(original_value, bool)
                        or not isinstance(
                            original_value, (int, float, np.number)
                        )
                        or not math.isfinite(float(original_value))
                        or float(original_value) <= 0.0
                    ):
                        protocol_failures.append("target_baseline_friction_invalid")
                    if not _positive_zero(ablated_value):
                        protocol_failures.append(
                            "target_friction_not_positive_zero"
                        )
            elif before != after:
                protocol_failures.append("non_target_pair_changed")
        if target_count == 0:
            protocol_failures.append("target_pairs_missing")
    except (TypeError, ValueError) as exc:
        protocol_failures.append(str(exc))
    protocol_failures = sorted(set(protocol_failures))
    return {
        "protocol_valid": not protocol_failures,
        "isolated": not protocol_failures,
        "protocol_failures": protocol_failures,
        "target_pair_count": target_count,
    }


def evaluate_prohibited_mechanism_audit(
    audit: Mapping[str, Any]
) -> dict[str, Any]:
    protocol_failures = []
    try:
        if not isinstance(audit, Mapping):
            raise ValueError("probe_audit_mapping_required")
        coverage = audit.get("coverage")
        counts = audit.get("post_reset_counts")
        if (
            not isinstance(coverage, Mapping)
            or set(coverage) != set(REQUIRED_AUDIT_SURFACES)
            or any(coverage.get(name) is not True for name in REQUIRED_AUDIT_SURFACES)
        ):
            protocol_failures.append("audit_coverage_incomplete")
        required_counts = {
            "root_body_pose_velocity_writers",
            "kinematic_targets",
            "forces_torques_impulses",
            "force_fields",
            "software_gripper_attachments",
            "constraints_attachments",
            "forward_filters",
            "reverse_filters",
            "collision_group_changes",
            "raw_property_changes",
        }
        if (
            not isinstance(counts, Mapping)
            or set(counts) != required_counts
            or any(type(counts.get(name)) is not int for name in required_counts)
        ):
            protocol_failures.append("audit_counts_invalid")
        elif any(counts[name] != 0 for name in required_counts):
            protocol_failures.append("post_reset_prohibited_write")
        if audit.get("reset_root_write_count") != 1:
            protocol_failures.append("reset_root_write_contract")
        if audit.get("zero_write_epoch_opened") is not True:
            protocol_failures.append("zero_write_epoch_missing")
    except (TypeError, ValueError) as exc:
        protocol_failures.append(str(exc))
    protocol_failures = sorted(set(protocol_failures))
    return {
        "protocol_valid": not protocol_failures,
        "zero_write_valid": not protocol_failures,
        "protocol_failures": protocol_failures,
    }


def evaluate_prelift_parity(
    original: Mapping[str, Any], ablation: Mapping[str, Any]
) -> dict[str, Any]:
    """Evaluate the preregistered final pre-lift state parity contract."""
    failures = []
    try:
        if not isinstance(original, Mapping) or not isinstance(ablation, Mapping):
            raise ValueError("probe_prelift_parity_mapping_required")
        for field in ("controller_event_sha256", "action_sha256"):
            if original.get(field) != ablation.get(field):
                failures.append(field)
        vector_limits = {
            "nonfinger_joint_positions_rad": 1.0e-6,
            "nonfinger_joint_velocities_rad_s": 1.0e-5,
            "finger_joint_positions_rad": 1.0e-6,
            "finger_joint_velocities_rad_s": 1.0e-5,
            "tool_position_m": 1.0e-4,
            "source_position_m": 1.0e-4,
            "tool_linear_velocity_m_s": 1.0e-3,
            "source_linear_velocity_m_s": 1.0e-3,
            "tool_angular_velocity_rad_s": math.radians(0.1),
            "source_angular_velocity_rad_s": math.radians(0.1),
        }
        for field, limit in vector_limits.items():
            one = np.asarray(original.get(field), dtype=np.float64)
            two = np.asarray(ablation.get(field), dtype=np.float64)
            if (
                one.shape != two.shape
                or one.ndim != 1
                or not np.isfinite(one).all()
                or not np.isfinite(two).all()
                or float(np.linalg.norm(one - two)) > limit
            ):
                failures.append(field)
        for field in ("tool_orientation_wxyz", "source_orientation_wxyz"):
            if _quaternion_angle_degrees(original.get(field), ablation.get(field)) > 0.1:
                failures.append(field)
        for side in ("left", "right"):
            first_points = original.get(f"{side}_target_points_source_local_m")
            second_points = ablation.get(f"{side}_target_points_source_local_m")
            unique_minimum_distance_assignment(
                first_points,
                second_points,
                maximum_distance_m=0.001,
            )
            one = float(original.get(f"{side}_normal_impulse_n_s"))
            two = float(ablation.get(f"{side}_normal_impulse_n_s"))
            if not math.isfinite(one) or not math.isfinite(two) or abs(one - two) > 1.0e-5:
                failures.append(f"{side}_normal_impulse")
        if original.get("support_lifecycle") != ablation.get("support_lifecycle"):
            failures.append("support_lifecycle")
        support_one = original.get("support_points_source_local_m")
        support_two = ablation.get("support_points_source_local_m")
        support_assignment = unique_minimum_distance_assignment(
            support_one,
            support_two,
            maximum_distance_m=0.001,
        )
        anchors_one = original.get("support_anchors_source_local_m")
        anchors_two = ablation.get("support_anchors_source_local_m")
        if anchors_one == [] and anchors_two == []:
            anchor_assignment = {"assignment": []}
        else:
            anchor_assignment = unique_minimum_distance_assignment(
                anchors_one,
                anchors_two,
                maximum_distance_m=0.001,
            )
        first_support_records = original.get("support_point_records")
        second_support_records = ablation.get("support_point_records")
        if (
            not isinstance(first_support_records, Sequence)
            or not isinstance(second_support_records, Sequence)
            or len(first_support_records) != len(second_support_records)
        ):
            failures.append("support_point_authority")
        else:
            for first_index, second_index in enumerate(
                support_assignment["assignment"]
            ):
                first = first_support_records[first_index]
                second = second_support_records[second_index]
                normal_one = _finite_vector(
                    first.get("source_normal_world"),
                    field="support_normal",
                    unit=True,
                )
                normal_two = _finite_vector(
                    second.get("source_normal_world"),
                    field="support_normal",
                    unit=True,
                )
                angle = math.degrees(
                    math.acos(
                        float(np.clip(normal_one @ normal_two, -1.0, 1.0))
                    )
                )
                if (
                    angle > 0.1
                    or abs(
                        float(first.get("separation_m"))
                        - float(second.get("separation_m"))
                    )
                    > 0.0001
                ):
                    failures.append("support_point_parity")
        first_anchor_records = original.get("support_anchor_records")
        second_anchor_records = ablation.get("support_anchor_records")
        if (
            not isinstance(first_anchor_records, Sequence)
            or not isinstance(second_anchor_records, Sequence)
            or len(first_anchor_records) != len(second_anchor_records)
        ):
            failures.append("support_anchor_authority")
        else:
            for first_index, second_index in enumerate(
                anchor_assignment["assignment"]
            ):
                impulse_one = _finite_vector(
                    first_anchor_records[first_index].get(
                        "source_impulse_n_s"
                    ),
                    field="support_anchor_impulse",
                )
                impulse_two = _finite_vector(
                    second_anchor_records[second_index].get(
                        "source_impulse_n_s"
                    ),
                    field="support_anchor_impulse",
                )
                if float(np.linalg.norm(impulse_one - impulse_two)) > 1.0e-5:
                    failures.append("support_anchor_impulse_parity")
        for field in (
            "support_normal_impulse_n_s",
            "support_friction_anchor_norm_n_s",
        ):
            if abs(float(original.get(field)) - float(ablation.get(field))) > 1.0e-5:
                failures.append(field)
        for field in (
            "non_target_solver_cache_hex",
            "source_support_solver_cache_hex",
        ):
            if not isinstance(original.get(field), str) or original.get(field) != ablation.get(field):
                failures.append("solver_cache_authority")
        target_cache_one = original.get("target_normal_cache")
        target_cache_two = ablation.get("target_normal_cache")
        if (
            not isinstance(target_cache_one, Mapping)
            or not isinstance(target_cache_two, Mapping)
            or set(target_cache_one) != set(target_cache_two)
        ):
            failures.append("target_normal_cache_authority")
        else:
            for pair_id in target_cache_one:
                try:
                    one = np.frombuffer(
                        bytes.fromhex(target_cache_one[pair_id]),
                        dtype=np.dtype("<f4"),
                    ).astype(np.float64)
                    two = np.frombuffer(
                        bytes.fromhex(target_cache_two[pair_id]),
                        dtype=np.dtype("<f4"),
                    ).astype(np.float64)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "probe_target_normal_cache_bytes_invalid"
                    ) from exc
                if (
                    one.shape != two.shape
                    or not np.isfinite(one).all()
                    or not np.isfinite(two).all()
                    or (one.size and float(np.max(np.abs(one - two))) > 1.0e-5)
                ):
                    failures.append("target_normal_cache_parity")
        margins_one = original.get("predicate_margins")
        margins_two = ablation.get("predicate_margins")
        if (
            not isinstance(margins_one, Mapping)
            or not isinstance(margins_two, Mapping)
            or set(margins_one) != set(margins_two)
        ):
            failures.append("predicate_margins")
        else:
            for name in margins_one:
                one = float(margins_one[name])
                two = float(margins_two[name])
                if (
                    not math.isfinite(one)
                    or not math.isfinite(two)
                    or one == 0.0
                    or two == 0.0
                    or math.copysign(1.0, one) != math.copysign(1.0, two)
                    or abs(one - two) > 0.5 * min(abs(one), abs(two))
                ):
                    failures.append("predicate_margins")
                    break
    except (KeyError, TypeError, ValueError, np.linalg.LinAlgError) as exc:
        failures.append(str(exc))
    failures = sorted(set(failures))
    return {
        "protocol_valid": not failures,
        "passed": not failures,
        "protocol_failures": failures,
    }


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


def _process_group_members(process_group_id: int) -> list[int]:
    members = []
    proc = Path("/proc")
    if not proc.is_dir():
        raise RuntimeError("probe_procfs_unavailable")
    for candidate in proc.iterdir():
        if not candidate.name.isdigit():
            continue
        try:
            stat = (candidate / "stat").read_text(encoding="utf-8")
            closing = stat.rfind(")")
            fields = stat[closing + 2 :].split()
            if len(fields) > 2 and int(fields[2]) == process_group_id:
                members.append(int(candidate.name))
        except (FileNotFoundError, PermissionError, ValueError):
            continue
    return sorted(members)


def validate_process_quiescence(
    process: Any,
    *,
    process_group_members: Callable[[int], Sequence[int]] = _process_group_members,
    collector_closed: bool,
) -> dict[str, Any]:
    if process.poll() is None:
        raise RuntimeError("probe_process_leader_not_reaped")
    members = list(process_group_members(int(process.pid)))
    if members:
        raise RuntimeError(f"probe_process_group_not_quiescent:{members}")
    if collector_closed is not True:
        raise RuntimeError("probe_collector_not_closed")
    return {
        "quiescent": True,
        "leader_pid": int(process.pid),
        "returncode": int(process.returncode),
        "remaining_process_group_members": [],
        "collector_closed": True,
    }


def validate_output_confinement(
    root: str | os.PathLike[str], relative_paths: Sequence[str]
) -> dict[str, Any]:
    root_path = Path(root).resolve()
    if isinstance(relative_paths, (str, bytes, bytearray)) or not isinstance(
        relative_paths, Sequence
    ):
        raise ValueError("probe_output_paths_invalid")
    normalized = []
    for value in relative_paths:
        if not isinstance(value, str) or not value:
            raise ValueError("probe_output_path_escape")
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("probe_output_path_escape")
        candidate = (root_path / path).resolve()
        try:
            candidate.relative_to(root_path)
        except ValueError as exc:
            raise ValueError("probe_output_path_escape") from exc
        normalized.append(path.as_posix())
    return {"valid": True, "paths": normalized, "root": str(root_path)}


def protocol_no_go_report(
    *,
    treatment: str,
    run_nonce: str,
    parent_pid: int,
    child_pid: int,
    run_id: str,
    blocker_code: str,
    blocker_detail: str,
) -> dict[str, Any]:
    if treatment not in TREATMENTS:
        raise ValueError("probe_treatment_invalid")
    blocker = ProtocolBlocker(blocker_code, blocker_detail)
    return {
        "schema_version": 1,
        "manifest_type": CHILD_MANIFEST_TYPE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "lifecycle_status": "measurement_complete_pending_application_close",
        "shutdown_status": "pending",
        "treatment": treatment,
        "run_nonce": run_nonce,
        "parent_pid": parent_pid,
        "child_pid": child_pid,
        "run_id": run_id,
        "measurement_decision": "PROBE_PROTOCOL_NO_GO",
        "protocol_blockers": [
            {"code": blocker.code, "detail": blocker.detail}
        ],
        "physical_failure": False,
        "causal_pass": False,
    }


def _runtime_error_child_report(
    exc: BaseException,
    *,
    treatment: str,
    run_nonce: str,
    parent_pid: int,
    child_pid: int,
    run_id: str,
    phase: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "manifest_type": CHILD_MANIFEST_TYPE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "lifecycle_status": "runtime_error_pending_application_close",
        "shutdown_status": "pending",
        "treatment": treatment,
        "run_nonce": run_nonce,
        "parent_pid": parent_pid,
        "child_pid": child_pid,
        "run_id": run_id,
        "measurement_decision": "PROBE_RUNTIME_ERROR",
        "protocol_blockers": [],
        "physical_failure": False,
        "causal_pass": False,
        "fatal_error": {
            "phase": phase,
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        },
    }


def finalize_child_result(
    provisional: Mapping[str, Any],
    *,
    expected_treatment: str,
    expected_run_nonce: str,
    expected_parent_pid: int,
    expected_child_pid: int,
    child_command: Sequence[str],
    child_returncode: int,
    timed_out: bool,
    termination: str | None,
    cleanup_quiescent: bool,
) -> dict[str, Any]:
    identity_valid = bool(
        isinstance(provisional, Mapping)
        and provisional.get("schema_version") == 1
        and provisional.get("manifest_type") == CHILD_MANIFEST_TYPE
        and provisional.get("treatment") == expected_treatment
        and provisional.get("run_nonce") == expected_run_nonce
        and provisional.get("parent_pid") == expected_parent_pid
        and provisional.get("child_pid") == expected_child_pid
        and isinstance(provisional.get("run_id"), str)
        and provisional.get("run_id")
    )
    lifecycle_valid = bool(
        identity_valid
        and provisional.get("lifecycle_status")
        in {
            "measurement_complete_pending_application_close",
            "runtime_error_pending_application_close",
        }
        and provisional.get("measurement_decision")
        in {
            "PROBE_RUNTIME_ERROR",
            "PROBE_PROTOCOL_NO_GO",
            "ORIGINAL_EMPTY_BEAKER_CONTACT_LIFT_FAIL",
            "ORIGINAL_EMPTY_BEAKER_FRICTION_CAUSAL_PASS",
            "ZERO_FRICTION_CAUSALITY_FAIL",
        }
    )
    process_valid = bool(
        identity_valid
        and lifecycle_valid
        and not timed_out
        and child_returncode == 0
        and cleanup_quiescent
        and provisional.get("measurement_decision") != "PROBE_RUNTIME_ERROR"
    )
    result = copy.deepcopy(dict(provisional))
    result.update(
        {
            "finalized_at_utc": datetime.now(timezone.utc).isoformat(),
            "identity_valid": identity_valid,
            "process_valid": process_valid,
            "child_process": {
                "command": [str(value) for value in child_command],
                "returncode": int(child_returncode),
                "timed_out": bool(timed_out),
                "termination": termination,
                "cleanup_quiescent": bool(cleanup_quiescent),
            },
        }
    )
    if process_valid:
        result["decision"] = provisional["measurement_decision"]
        result["runtime_error"] = False
        result["lifecycle_status"] = "completed"
        result["shutdown_status"] = "child_exit_0"
        return result
    result["decision"] = "PROBE_RUNTIME_ERROR"
    result["runtime_error"] = True
    result["lifecycle_status"] = "failed"
    if not identity_valid:
        result["shutdown_status"] = "child_identity_invalid"
    elif timed_out:
        result["shutdown_status"] = "child_timeout"
    elif child_returncode != 0:
        result["shutdown_status"] = "child_exit_nonzero"
    elif not cleanup_quiescent:
        result["shutdown_status"] = "cleanup_not_quiescent"
    else:
        result["shutdown_status"] = "child_runtime_error"
    return result


def _artifact_record(path: Path, *, relative_to: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(relative_to).as_posix(),
        "byte_count": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _validate_artifact_record(
    record: Mapping[str, Any], *, treatment_dir: Path
) -> Path:
    if not isinstance(record, Mapping):
        raise ValueError("probe_artifact_record_invalid")
    relative = record.get("path")
    if not isinstance(relative, str):
        raise ValueError("probe_artifact_path_invalid")
    validate_output_confinement(treatment_dir, [relative])
    path = treatment_dir / relative
    if (
        not path.is_file()
        or type(record.get("byte_count")) is not int
        or path.stat().st_size != record["byte_count"]
        or not _is_sha256(record.get("sha256"))
        or sha256_file(path) != record["sha256"]
    ):
        raise ValueError("probe_artifact_hash_mismatch")
    return path


def _validate_child_artifacts(
    provisional: Mapping[str, Any],
    *,
    treatment_dir: Path,
    expected_config_sha256: str,
    expected_parent_pid: int,
    expected_child_pid: int,
    expected_nonce: str,
) -> dict[str, Any]:
    artifacts = provisional.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {
        "frozen_config",
        "trace",
    }:
        raise ValueError("probe_artifact_set_invalid")
    config_path = _validate_artifact_record(
        artifacts["frozen_config"], treatment_dir=treatment_dir
    )
    trace_path = _validate_artifact_record(
        artifacts["trace"], treatment_dir=treatment_dir
    )
    if sha256_file(config_path) != expected_config_sha256:
        raise ValueError("probe_frozen_config_hash_mismatch")
    records = load_strict_jsonl(trace_path)
    trace = validate_trace_records(
        records,
        expected_treatment=str(provisional["treatment"]),
        expected_run_nonce=expected_nonce,
        expected_parent_pid=expected_parent_pid,
        expected_child_pid=expected_child_pid,
        expected_run_id=str(provisional["run_id"]),
    )
    if provisional.get("trace_chain_sha256") != trace["chain_sha256"]:
        raise ValueError("probe_trace_summary_contradiction")
    return {"trace": trace, "records": records}


def _implementation_identity(config: Mapping[str, Any]) -> dict[str, Any]:
    diagnostic = config.get("diagnostic")
    files = diagnostic.get("required_implementation_files") if isinstance(
        diagnostic, Mapping
    ) else None
    if (
        not isinstance(files, Sequence)
        or isinstance(files, (str, bytes, bytearray))
        or not files
    ):
        raise ValueError("probe_identity_implementation_files_invalid")
    hashes = {}
    for relative in files:
        if not isinstance(relative, str):
            raise ValueError("probe_identity_implementation_files_invalid")
        path = (REPO_ROOT / relative).resolve()
        try:
            path.relative_to(REPO_ROOT)
        except ValueError as exc:
            raise ValueError("probe_identity_implementation_path_escape") from exc
        if not path.is_file():
            raise ValueError(f"probe_identity_file_missing:{relative}")
        hashes[relative] = sha256_file(path)
    runner = Path(__file__).resolve()
    asset = (REPO_ROOT / str(config["usd_path"])).resolve()
    if not asset.is_file():
        raise ValueError(f"probe_identity_asset_missing:{asset}")
    payload = {
        "python_executable": str(Path(sys.executable).resolve()),
        "runner_sha256": sha256_file(runner),
        "asset": {"path": str(asset), "sha256": sha256_file(asset)},
        "implementation_files": hashes,
    }
    return {**payload, "identity_sha256": _canonical_json_sha256(payload)}


def _extract_transition_payloads(
    trace_records: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    return [
        record["payload"]
        for record in trace_records
        if record.get("kind") == "transition"
    ]


def validate_runtime_transition_ledger(
    transitions: Sequence[Mapping[str, Any]], *, maximum_production_steps: int
) -> dict[str, Any]:
    production = [
        record
        for record in transitions
        if record.get("continuation_index") is None
    ]
    apply_index = 0
    ledger = []
    for record in production:
        action = record.get("canonical_action")
        raw_action = record.get("raw_action")
        if (action is None) != (raw_action is None):
            raise ValueError("probe_runtime_action_authority_mismatch")
        if action is not None and canonicalize_action(raw_action) != action:
            raise ValueError("probe_runtime_action_hash_mismatch")
        applies = record.get("apply_count")
        ledger.append(
            {
                "transition_index": int(record["transition_index"]),
                "state_present": record.get("controller_call_count") == 1,
                "controller_call_count": record.get("controller_call_count"),
                "native_event": record.get("native_event"),
                "action": action,
                "apply_count": applies,
                "apply_index": apply_index if action is not None else None,
                "integrating_transition_index": (
                    int(record["transition_index"]) + 1
                    if action is not None
                    else None
                ),
                "phase_after": record.get("phase_after"),
                "terminal_outcome": record.get("terminal_outcome"),
            }
        )
        if action is not None:
            apply_index += 1
    summary = validate_action_ledger(
        ledger, maximum_production_steps=maximum_production_steps
    )
    integrated_lift = _lift_transition(transitions)
    if summary["k_lift"] != integrated_lift:
        raise ValueError(
            "probe_runtime_ledger_lift_transition_mismatch:"
            f"ledger={summary['k_lift']}:trace={integrated_lift}"
        )
    continuation = [
        record
        for record in transitions
        if record.get("continuation_index") is not None
    ]
    if any(
        record.get("controller_call_count") != 0
        or record.get("canonical_action") is not None
        or record.get("raw_action") is not None
        or record.get("apply_count") != 0
        for record in continuation
    ):
        raise ValueError("probe_runtime_continuation_action_invalid")
    return {
        **summary,
        "continuation_count": len(continuation),
        "no_continuation_actions": True,
    }


def recompute_instrumented_contact_trace(
    transitions: Sequence[Mapping[str, Any]],
    *,
    runtime_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    from utils.controlled_contact import FullContactReportAccumulator

    geometry = runtime_evidence.get("geometry")
    orientation = runtime_evidence.get("orientation_calibration")
    source_contract = runtime_evidence.get("source_contract")
    stage_id = runtime_evidence.get("stage_id")
    if (
        not isinstance(geometry, Mapping)
        or not isinstance(orientation, Mapping)
        or not isinstance(source_contract, Mapping)
        or type(stage_id) is not int
    ):
        raise ValueError("probe_parent_contact_runtime_authority_missing")
    source_collider = str(source_contract["source_collider_path"])
    support_collider = "/World/Cube"
    target_pairs = {
        _runtime_pair_key(
            str(target["source_collider"]),
            str(target["finger_collider"]),
        ): str(target["side"])
        for target in geometry.get("target_pairs", [])
    }
    accumulator = FullContactReportAccumulator(
        expected_stage_id=stage_id,
        provisional_background_pairs=((source_collider, support_collider),),
    )
    contact_sha256 = []
    for index, transition in enumerate(transitions):
        contact = transition.get("contact")
        if not isinstance(contact, Mapping):
            raise ValueError("probe_parent_contact_payload_missing")
        raw = contact.get("raw_report")
        if not isinstance(raw, Mapping):
            raise ValueError("probe_parent_raw_contact_report_missing")
        if (
            raw.get("authority")
            != "probe_complete_physx_contact_report_v1"
            or raw.get("physics_index") != index
            or raw.get("immediate_read_index") != index
        ):
            raise ValueError("probe_parent_contact_read_index_mismatch")
        normalized = accumulator.consume(
            physics_index=index,
            headers=raw.get("all_headers"),
            contact_data=raw.get("all_contact_data"),
            friction_anchors=raw.get("all_friction_anchors"),
            allow_provisional_persist_bootstrap=index == 0,
        )
        for field in (
            "event_sequences",
            "current_pairs",
            "occurrences",
            "header_count",
            "contact_data_count",
            "friction_anchor_count",
        ):
            if normalized.get(field) != raw.get(field):
                raise ValueError(
                    f"probe_parent_contact_normalization_mismatch:{index}:{field}"
                )
        recomputed = _runtime_contact_evidence(
            raw,
            geometry=geometry,
            source_collider=source_collider,
            support_collider=support_collider,
            target_pairs=target_pairs,
            orientation=orientation,
            aperture_rate_m_s=float(
                transition["post"]["finger_aperture_rate_m_s"]
            ),
        )
        for field in (
            "bilateral_qualified",
            "prohibited_contact",
            "left_friction_anchor_norm_n_s",
            "right_friction_anchor_norm_n_s",
            "support_event",
            "support_contact_count",
            "support_friction_anchor_count",
            "support_impulse_n_s",
            "geometry",
            "reduced_occurrences",
        ):
            if _canonical_json_bytes(recomputed.get(field)) != _canonical_json_bytes(
                contact.get(field)
            ):
                raise ValueError(
                    f"probe_parent_contact_reduction_mismatch:{index}:{field}"
                )
        if recomputed["support_current"] is not transition["post"].get(
            "support_current"
        ):
            raise ValueError(
                f"probe_parent_support_state_mismatch:{index}"
            )
        contact_sha256.append(
            _canonical_json_sha256(
                {
                    key: recomputed[key]
                    for key in recomputed
                    if key != "raw_report"
                }
            )
        )
    return {
        "valid": True,
        "transition_count": len(transitions),
        "contact_sha256": contact_sha256,
        "trace_sha256": _canonical_json_sha256(contact_sha256),
    }


def recompute_transition_states(
    transitions: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    if not transitions:
        raise ValueError("probe_parent_transition_states_missing")
    prior_world = None
    prior_post = None
    prior_robot_post = None
    lift_reference = None
    lift_index = None
    for index, transition in enumerate(transitions):
        if transition.get("transition_index") != index:
            raise ValueError("probe_parent_transition_index_mismatch")
        world_index = transition.get("world_index")
        if type(world_index) is not int or (
            prior_world is not None and world_index != prior_world + 1
        ):
            raise ValueError("probe_parent_world_index_discontinuous")
        before = transition.get("authority_pre")
        after = transition.get("authority_post")
        robot_before = transition.get("robot_pre")
        robot_after = transition.get("robot_post")
        if not isinstance(before, Mapping) or not isinstance(after, Mapping):
            raise ValueError("probe_parent_state_authority_missing")
        if not isinstance(robot_before, Mapping) or not isinstance(
            robot_after, Mapping
        ):
            raise ValueError("probe_parent_robot_state_authority_missing")
        if prior_post is not None and _canonical_json_bytes(before) != _canonical_json_bytes(
            prior_post
        ):
            raise ValueError("probe_parent_state_continuity_mismatch")
        if prior_robot_post is not None and _canonical_json_bytes(
            robot_before
        ) != _canonical_json_bytes(prior_robot_post):
            raise ValueError("probe_parent_robot_state_continuity_mismatch")
        for authority, compact_name in ((before, "pre"), (after, "post")):
            compact = transition.get(compact_name)
            if not isinstance(compact, Mapping):
                raise ValueError("probe_parent_compact_state_missing")
            com = _finite_vector(
                authority.get("source_com_m"), field="parent_source_com"
            )
            linear = _finite_vector(
                authority.get("source_linear_velocity_m_s"),
                field="parent_source_linear_velocity",
            )
            angular = _finite_vector(
                authority.get("source_angular_velocity_rad_s"),
                field="parent_source_angular_velocity",
            )
            if (
                not np.array_equal(
                    com,
                    np.asarray(compact.get("source_com_m"), dtype=np.float64),
                )
                or not math.isclose(
                    float(np.linalg.norm(linear)),
                    float(compact.get("source_linear_speed_m_s")),
                    rel_tol=0.0,
                    abs_tol=1.0e-12,
                )
                or not math.isclose(
                    math.degrees(float(np.linalg.norm(angular))),
                    float(compact.get("source_angular_speed_degrees_s")),
                    rel_tol=0.0,
                    abs_tol=1.0e-12,
                )
            ):
                raise ValueError("probe_parent_compact_state_contradiction")
            robot_state = robot_before if compact_name == "pre" else robot_after
            joint_positions = np.asarray(
                robot_state.get("joint_positions_rad"), dtype=np.float64
            )
            joint_velocities = np.asarray(
                robot_state.get("joint_velocities_rad_s"), dtype=np.float64
            )
            if (
                joint_positions.ndim != 1
                or len(joint_positions) <= 8
                or joint_velocities.shape != joint_positions.shape
                or not np.isfinite(joint_positions).all()
                or not np.isfinite(joint_velocities).all()
                or not math.isclose(
                    abs(float(joint_velocities[7] + joint_velocities[8])),
                    float(compact.get("finger_aperture_rate_m_s")),
                    rel_tol=0.0,
                    abs_tol=1.0e-12,
                )
            ):
                raise ValueError("probe_parent_robot_state_contradiction")
        receipt = transition.get("action_receipt")
        if isinstance(receipt, Mapping) and receipt.get("native_event") == 5:
            if lift_reference is not None:
                raise ValueError("probe_parent_multiple_lift_receipts")
            source = np.asarray(before["source_world_matrix"], dtype=np.float64)
            tool = np.asarray(before["tool_world_matrix"], dtype=np.float64)
            lift_reference = source @ np.linalg.inv(tool)
            lift_index = index
        if lift_reference is not None:
            translation, rotation = _relative_pose_drift(
                lift_reference,
                after["source_world_matrix"],
                after["tool_world_matrix"],
            )
            contact = transition.get("contact")
            if (
                not isinstance(contact, Mapping)
                or not math.isclose(
                    translation,
                    float(contact.get("source_tool_drift_translation_m")),
                    rel_tol=0.0,
                    abs_tol=1.0e-12,
                )
                or not math.isclose(
                    rotation,
                    float(contact.get("source_tool_drift_rotation_degrees")),
                    rel_tol=0.0,
                    abs_tol=1.0e-9,
                )
            ):
                raise ValueError("probe_parent_drift_recalculation_mismatch")
        prior_world = world_index
        prior_post = after
        prior_robot_post = robot_after
    if lift_index is None:
        raise ValueError("probe_parent_lift_receipt_missing")
    return {
        "valid": True,
        "transition_count": len(transitions),
        "first_world_index": transitions[0]["world_index"],
        "last_world_index": transitions[-1]["world_index"],
        "k_lift": lift_index,
    }


def validate_cross_treatment_runtime_contract(
    child_results: Mapping[str, Mapping[str, Any]],
    *,
    expected_config_sha256: str,
) -> dict[str, Any]:
    failures = []
    identities = {}
    for treatment in TREATMENTS:
        result = child_results.get(treatment)
        evidence = result.get("runtime_evidence") if isinstance(result, Mapping) else None
        if not isinstance(evidence, Mapping):
            failures.append(f"{treatment}:runtime_evidence_missing")
            continue
        scene = evidence.get("scene_identity")
        source = evidence.get("source_contract")
        if not isinstance(scene, Mapping) or scene.get("valid") is not True:
            failures.append(f"{treatment}:scene_identity")
        if not isinstance(source, Mapping) or source.get("valid") is not True:
            failures.append(f"{treatment}:source_contract")
        if evidence.get("backend") != "numpy" or evidence.get(
            "gpu_override_requested"
        ) is not False:
            failures.append(f"{treatment}:backend")
        if evidence.get("reset_count") != 2:
            failures.append(f"{treatment}:reset_count")
        comparison = result.get("comparison_summary")
        if (
            not isinstance(comparison, Mapping)
            or comparison.get("config_sha256") != expected_config_sha256
        ):
            failures.append(f"{treatment}:config_identity")
        report_layer = evidence.get("report_layer")
        ablation_delta = evidence.get("ablation_delta")
        if treatment == "control":
            if report_layer is not None or ablation_delta is not None:
                failures.append("control:probe_authored_delta")
        elif treatment == "instrumented_original":
            if not isinstance(report_layer, Mapping) or ablation_delta is not None:
                failures.append("instrumented_original:stage_delta")
        else:
            if not isinstance(report_layer, Mapping) or not isinstance(
                ablation_delta, Mapping
            ):
                failures.append("zero_friction_ablation:stage_delta")
        identities[treatment] = {
            "scene": scene,
            "dependency_closure_sha256": evidence.get(
                "dependency_closure", {}
            ).get("sha256"),
            "default_franka_sha256": evidence.get(
                "default_franka_identity", {}
            ).get("sha256"),
            "version_and_gpu_sha256": evidence.get(
                "version_and_gpu_identity", {}
            ).get("sha256"),
            "orientation_calibration_sha256": evidence.get(
                "orientation_calibration", {}
            ).get("setup_sha256"),
            "orientation_result_sha256": (
                _canonical_json_sha256(evidence["orientation_calibration"])
                if isinstance(evidence.get("orientation_calibration"), Mapping)
                else None
            ),
            "requested_source_position_m": evidence.get(
                "requested_source_position_m"
            ),
            "readback_source_position_m": evidence.get(
                "readback_source_position_m"
            ),
        }
    if len(identities) == len(TREATMENTS):
        control_identity = identities["control"]
        for treatment in TREATMENTS[1:]:
            if identities[treatment] != control_identity:
                failures.append(f"{treatment}:cross_treatment_identity")
    failures = sorted(set(failures))
    return {
        "protocol_valid": not failures,
        "protocol_failures": failures,
        "identities": identities,
    }


def recompute_final_evidence(
    child_results: Mapping[str, Mapping[str, Any]],
    trace_records: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    runtime_error = bool(
        set(child_results) != set(TREATMENTS)
        or set(trace_records) != set(TREATMENTS)
        or any(result.get("runtime_error") is True for result in child_results.values())
    )
    protocol_no_go = False
    perturbation = False
    original_lift = False
    retention = False
    ablation_causal = False
    evaluations: dict[str, Any] = {}
    if not runtime_error:
        protocol_no_go = any(
            result.get("decision") == "PROBE_PROTOCOL_NO_GO"
            for result in child_results.values()
        )
    diagnostic = config.get("diagnostic", {})
    if not runtime_error and not protocol_no_go:
        try:
            runtime_contract = validate_cross_treatment_runtime_contract(
                child_results,
                expected_config_sha256=_sha256_bytes(
                    _canonical_json_bytes(config)
                ),
            )
            instrumented_trace = _extract_transition_payloads(
                trace_records["instrumented_original"]
            )
            ablation_trace = _extract_transition_payloads(
                trace_records["zero_friction_ablation"]
            )
            transition_traces = {
                treatment: _extract_transition_payloads(
                    trace_records[treatment]
                )
                for treatment in TREATMENTS
            }
            ledgers = {
                treatment: validate_runtime_transition_ledger(
                    transition_traces[treatment],
                    maximum_production_steps=int(
                        diagnostic["maximum_production_steps"]
                    ),
                )
                for treatment in TREATMENTS
            }
            state_reductions = {
                treatment: recompute_transition_states(
                    transition_traces[treatment]
                )
                for treatment in TREATMENTS
            }
            contact_reductions = {
                treatment: recompute_instrumented_contact_trace(
                    transition_traces[treatment],
                    runtime_evidence=child_results[treatment][
                        "runtime_evidence"
                    ],
                )
                for treatment in (
                    "instrumented_original",
                    "zero_friction_ablation",
                )
            }
            original_evaluation = evaluate_original_lift_trace(
                instrumented_trace,
                physics_dt=float(diagnostic["physics_dt"]),
                retention_steps=int(diagnostic["retention_steps"]),
                rise_threshold_m=float(diagnostic["rise_threshold_m"]),
            )
            ablation_evaluation = evaluate_zero_friction_trace(
                ablation_trace,
                retention_steps=int(diagnostic["retention_steps"]),
                rise_threshold_m=float(diagnostic["rise_threshold_m"]),
                maximum_rise_m=float(diagnostic["maximum_ablation_rise_m"]),
                maximum_friction_anchor_norm_n_s=float(
                    diagnostic["maximum_zero_friction_anchor_norm_n_s"]
                ),
            )
            comparison = compare_control_and_instrumented(
                child_results["control"]["comparison_summary"],
                child_results["instrumented_original"]["comparison_summary"],
            )
            pair_table = evaluate_ablation_pair_table(
                child_results["instrumented_original"]["effective_pair_table"],
                child_results["zero_friction_ablation"]["effective_pair_table"],
            )
            parity = evaluate_prelift_parity(
                child_results["instrumented_original"]["prelift_parity"],
                child_results["zero_friction_ablation"]["prelift_parity"],
            )
            audits = {
                treatment: evaluate_prohibited_mechanism_audit(
                    child_results[treatment]["prohibited_mechanism_audit"]
                )
                for treatment in TREATMENTS
            }
            protocol_no_go = bool(
                not runtime_contract["protocol_valid"]
                or not original_evaluation["protocol_valid"]
                or not ablation_evaluation["protocol_valid"]
                or not pair_table["protocol_valid"]
                or not parity["protocol_valid"]
                or any(not audit["protocol_valid"] for audit in audits.values())
            )
            perturbation = comparison["perturbation_detected"]
            original_lift = original_evaluation["contact_lift_passed"]
            retention = original_evaluation["retention_passed"]
            ablation_causal = bool(
                ablation_evaluation["causal_negative_passed"]
                and pair_table["isolated"]
                and parity["passed"]
            )
            evaluations = {
                "instrumented_original": original_evaluation,
                "runtime_contract": runtime_contract,
                "zero_friction_ablation": ablation_evaluation,
                "control_instrumented_comparison": comparison,
                "ablation_pair_table": pair_table,
                "prelift_parity": parity,
                "prohibited_mechanism_audits": audits,
                "action_ledgers": ledgers,
                "transition_states": state_reductions,
                "contact_reductions": contact_reductions,
            }
        except (KeyError, TypeError, ValueError) as exc:
            protocol_no_go = True
            evaluations = {
                "parent_recalculation_error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
            }
    components = {
        "runtime_error": runtime_error,
        "protocol_no_go": protocol_no_go,
        "contact_report_perturbation": perturbation,
        "original_contact_lift_passed": original_lift,
        "retention_continuation_passed": retention,
        "zero_friction_causality_passed": ablation_causal,
    }
    return {
        "components": components,
        "decision": select_decision(components),
        "evaluations": evaluations,
    }


def _runtime_world_counter(world: Any) -> int:
    value = getattr(world, "current_time_step_index", None)
    value = value() if callable(value) else value
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ProtocolBlocker(
            "world_counter_authority_unavailable",
            "World.current_time_step_index is not an integer authority",
        )
    return int(value)


def _runtime_row_matrix(stage: Any, path: str) -> np.ndarray:
    from pxr import Usd, UsdGeom

    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        raise ProtocolBlocker("runtime_prim_missing", path)
    matrix = np.asarray(
        UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
            Usd.TimeCode.Default()
        ),
        dtype=np.float64,
    )
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ProtocolBlocker("runtime_world_matrix_invalid", path)
    return matrix


def _runtime_enabled_colliders(stage: Any, body_path: str) -> list[str]:
    from pxr import Usd, UsdPhysics

    body = stage.GetPrimAtPath(body_path)
    if not body or not body.IsValid():
        raise ProtocolBlocker("runtime_body_missing", body_path)
    result = []
    for prim in Usd.PrimRange(body):
        if not prim.HasAPI(UsdPhysics.CollisionAPI):
            continue
        enabled = UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()
        if enabled is not False:
            result.append(str(prim.GetPath()))
    if not result:
        raise ProtocolBlocker(
            "runtime_enabled_finger_colliders_missing", body_path
        )
    return sorted(result)


def _runtime_bound(stage: Any, path: str) -> dict[str, Any]:
    from pxr import Usd, UsdGeom

    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        raise ProtocolBlocker("runtime_bound_prim_missing", path)
    cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        includedPurposes=[
            UsdGeom.Tokens.default_,
            UsdGeom.Tokens.proxy,
            UsdGeom.Tokens.render,
        ],
        useExtentsHint=False,
        ignoreVisibility=True,
    )
    bound = cache.ComputeLocalBound(prim)
    extent = bound.GetRange()
    low = [float(value) for value in extent.GetMin()]
    high = [float(value) for value in extent.GetMax()]
    bbox_matrix = np.asarray(bound.GetMatrix(), dtype=np.float64)
    parent = prim.GetParent()
    parent_matrix = np.asarray(
        UsdGeom.Xformable(parent).ComputeLocalToWorldTransform(
            Usd.TimeCode.Default()
        ),
        dtype=np.float64,
    )
    record = {
        "path": path,
        "range_min_m": low,
        "range_max_m": high,
        "bbox_matrix": bbox_matrix.tolist(),
        "parent_world_matrix": parent_matrix.tolist(),
    }
    transform_sealed_bound(record)
    return record


def _runtime_report_api_inventory(stage: Any) -> dict[str, Any]:
    from pxr import PhysxSchema, Usd

    records = []
    for prim in Usd.PrimRange.Stage(stage):
        if not prim.HasAPI(PhysxSchema.PhysxContactReportAPI):
            continue
        api = PhysxSchema.PhysxContactReportAPI(prim)
        threshold = api.GetThresholdAttr()
        pairs = api.GetReportPairsRel()
        records.append(
            {
                "path": str(prim.GetPath()),
                "threshold": (
                    float(threshold.Get())
                    if threshold and threshold.Get() is not None
                    else None
                ),
                "report_pairs": (
                    sorted(str(path) for path in pairs.GetTargets())
                    if pairs
                    else []
                ),
            }
        )
    records.sort(key=lambda item: item["path"])
    return {
        "records": records,
        "sha256": _canonical_json_sha256(records),
    }


def _runtime_install_report_layer(
    stage: Any,
    *,
    source_body_path: str,
    robot_report_body_paths: Sequence[str],
) -> dict[str, Any]:
    from pxr import PhysxSchema, Sdf, Usd

    session = stage.GetSessionLayer()
    if session is None:
        raise ProtocolBlocker(
            "report_session_layer_unavailable", "stage has no session layer"
        )
    previous_target = stage.GetEditTarget()
    previous_identifier = previous_target.GetLayer().identifier
    previous_sublayers = list(session.subLayerPaths)
    layer = Sdf.Layer.CreateAnonymous("original_empty_contact_lift_probe.usda")
    if layer is None:
        raise ProtocolBlocker(
            "report_session_sublayer_unavailable",
            "Sdf.Layer.CreateAnonymous returned no layer",
        )
    edits = []
    try:
        session.subLayerPaths.insert(0, layer.identifier)
        stage.SetEditTarget(Usd.EditTarget(layer))
        for path in (source_body_path, *robot_report_body_paths):
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                raise ProtocolBlocker("report_body_missing", path)
            existing = prim.HasAPI(PhysxSchema.PhysxContactReportAPI)
            api = (
                PhysxSchema.PhysxContactReportAPI(prim)
                if existing
                else PhysxSchema.PhysxContactReportAPI.Apply(prim)
            )
            threshold = api.GetThresholdAttr()
            current_threshold = (
                float(threshold.Get())
                if threshold and threshold.Get() is not None
                else None
            )
            pairs = api.GetReportPairsRel()
            current_pairs = (
                [str(value) for value in pairs.GetTargets()] if pairs else []
            )
            reused = bool(
                existing and current_threshold == 0.0 and current_pairs == []
            )
            if not reused:
                api.CreateThresholdAttr().Set(0.0)
                api.CreateReportPairsRel().SetTargets([])
            read_threshold = api.GetThresholdAttr().Get()
            read_pairs = list(api.GetReportPairsRel().GetTargets())
            if float(read_threshold) != 0.0 or read_pairs:
                raise ProtocolBlocker(
                    "report_api_readback_mismatch", path
                )
            edits.append(
                {
                    "path": path,
                    "existing_api": existing,
                    "reused_without_edit": reused,
                    "threshold": 0.0,
                    "report_pairs": [],
                }
            )
    finally:
        stage.SetEditTarget(previous_target)
    if stage.GetEditTarget().GetLayer().identifier != previous_identifier:
        raise ProtocolBlocker(
            "report_edit_target_restore_failed", previous_identifier
        )
    if list(session.subLayerPaths) != [layer.identifier, *previous_sublayers]:
        raise ProtocolBlocker(
            "report_session_sublayer_order_invalid", layer.identifier
        )
    return {
        "layer_identifier": layer.identifier,
        "layer_sha256": _sha256_bytes(layer.ExportToString().encode("utf-8")),
        "production_edit_target_identifier": previous_identifier,
        "edits": edits,
        "authored_catalog": _runtime_layer_catalog(layer),
        "layer": layer,
    }


def _runtime_layer_catalog(layer: Any) -> dict[str, Any]:
    records = []

    def visit(prim_spec: Any) -> None:
        records.append(
            {
                "path": str(prim_spec.path),
                "specifier": str(prim_spec.specifier),
                "type_name": str(prim_spec.typeName or ""),
                "properties": sorted(
                    property_spec.name for property_spec in prim_spec.properties
                ),
                "info_keys": sorted(str(key) for key in prim_spec.ListInfoKeys()),
            }
        )
        for child in prim_spec.nameChildren:
            visit(child)

    for root in layer.rootPrims:
        visit(root)
    records.sort(key=lambda item: item["path"])
    payload = {"records": records}
    return {**payload, "sha256": _canonical_json_sha256(payload)}


def _validate_report_only_layer_catalog(
    catalog: Mapping[str, Any], *, report_body_paths: Sequence[str]
) -> dict[str, Any]:
    records = catalog.get("records")
    if not isinstance(records, Sequence):
        raise ProtocolBlocker(
            "report_layer_catalog_invalid", str(catalog)
        )
    expected = set(report_body_paths)
    allowed_paths = {"/"}
    for path in expected:
        current = Path(path)
        while str(current) not in {".", "/"}:
            allowed_paths.add(current.as_posix())
            current = current.parent
        allowed_paths.add("/World")
    for record in records:
        path = record.get("path")
        properties = set(record.get("properties", []))
        if path not in allowed_paths:
            raise ProtocolBlocker(
                "report_layer_unexpected_prim", str(path)
            )
        if path in expected:
            if not properties <= {
                "physxContactReport:threshold",
                "physxContactReport:reportPairs",
            }:
                raise ProtocolBlocker(
                    "report_layer_unexpected_property",
                    f"{path}:{sorted(properties)}",
                )
        elif properties:
            raise ProtocolBlocker(
                "report_layer_ancestor_property", f"{path}:{sorted(properties)}"
            )
    return {
        "valid": True,
        "report_body_paths": sorted(expected),
        "catalog_sha256": catalog.get("sha256"),
    }


def _validate_ablation_layer_catalog(
    catalog: Mapping[str, Any],
    *,
    report_body_paths: Sequence[str],
    finger_colliders: Sequence[str],
    material_path: str,
    source_root_path: str,
    support_path: str,
) -> dict[str, Any]:
    records = catalog.get("records")
    if not isinstance(records, Sequence):
        raise ProtocolBlocker(
            "ablation_layer_catalog_invalid", str(catalog)
        )
    report_paths = set(report_body_paths)
    collider_paths = set(finger_colliders)
    terminal_paths = report_paths | collider_paths | {material_path}
    allowed_paths = set()
    for path in terminal_paths:
        current = Path(path)
        while str(current) not in {".", "/"}:
            allowed_paths.add(current.as_posix())
            current = current.parent
        allowed_paths.add("/World")
    for record in records:
        path = str(record.get("path"))
        properties = set(record.get("properties", []))
        if path == source_root_path or path == support_path or path.startswith(
            source_root_path + "/"
        ) and path not in report_paths:
            if properties:
                raise ProtocolBlocker(
                    "ablation_authored_source_or_support_opinion",
                    f"{path}:{sorted(properties)}",
                )
        if path not in allowed_paths:
            raise ProtocolBlocker(
                "ablation_layer_unexpected_prim", path
            )
        if path in report_paths:
            if not properties <= {
                "physxContactReport:threshold",
                "physxContactReport:reportPairs",
            }:
                raise ProtocolBlocker(
                    "ablation_report_property_changed",
                    f"{path}:{sorted(properties)}",
                )
        elif path in collider_paths:
            if properties != {"material:binding:physics"}:
                raise ProtocolBlocker(
                    "ablation_finger_binding_delta_invalid",
                    f"{path}:{sorted(properties)}",
                )
        elif path == material_path:
            if not properties or any(
                not (
                    name.startswith("physics:")
                    or name.startswith("physxMaterial:")
                )
                for name in properties
            ):
                raise ProtocolBlocker(
                    "ablation_material_delta_invalid",
                    f"{path}:{sorted(properties)}",
                )
        elif properties:
            raise ProtocolBlocker(
                "ablation_ancestor_property",
                f"{path}:{sorted(properties)}",
            )
    return {
        "valid": True,
        "catalog_sha256": catalog.get("sha256"),
        "finger_colliders": sorted(collider_paths),
        "material_path": material_path,
    }


def _runtime_material_binding(stage: Any, path: str) -> dict[str, Any]:
    from pxr import PhysxSchema, Usd, UsdPhysics, UsdShade

    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        raise ProtocolBlocker("material_target_missing", path)
    for descendant in Usd.PrimRange(prim):
        if descendant == prim or descendant.GetTypeName() != "GeomSubset":
            continue
        binding_relationships = [
            relationship
            for relationship in descendant.GetRelationships()
            if relationship.GetName().startswith("material:binding")
            and relationship.GetTargets()
        ]
        if binding_relationships:
            raise ProtocolBlocker(
                "per_face_material_authority_unsupported",
                f"{path}:{descendant.GetPath()}",
            )
    binding = UsdShade.MaterialBindingAPI(prim)
    try:
        computed = binding.ComputeBoundMaterial("physics")
    except TypeError:
        computed = binding.ComputeBoundMaterial(materialPurpose="physics")
    material = computed[0] if isinstance(computed, tuple) else computed
    relationship = computed[1] if isinstance(computed, tuple) and len(computed) > 1 else None
    material_prim = material.GetPrim() if material else None
    if not material_prim or not material_prim.IsValid():
        raise ProtocolBlocker("material_binding_unresolved", path)
    physics = UsdPhysics.MaterialAPI(material_prim)
    if not physics:
        raise ProtocolBlocker(
            "physics_material_schema_missing", str(material_prim.GetPath())
        )
    values = {}
    for name, getter in (
        ("static_friction", physics.GetStaticFrictionAttr),
        ("dynamic_friction", physics.GetDynamicFrictionAttr),
        ("restitution", physics.GetRestitutionAttr),
        ("density", physics.GetDensityAttr),
    ):
        attribute = getter()
        raw = attribute.Get() if attribute else None
        values[name] = float(raw) if raw is not None else None
    physx = PhysxSchema.PhysxMaterialAPI(material_prim)
    generic = {}
    for attribute in material_prim.GetAttributes():
        name = attribute.GetName()
        if not (
            name.startswith("physics:") or name.startswith("physxMaterial:")
        ):
            continue
        value = attribute.Get()
        generic[name] = _json_native(value)
    return {
        "target_path": path,
        "material_path": str(material_prim.GetPath()),
        "binding_relationship": (
            relationship.GetName() if relationship else None
        ),
        "binding_owner_path": (
            str(relationship.GetPrim().GetPath()) if relationship else None
        ),
        "binding_resolution_kind": (
            "collection"
            if relationship and "collection" in relationship.GetName()
            else "direct"
            if relationship
            and str(relationship.GetPrim().GetPath()) == path
            else "inherited"
        ),
        "binding_targets": (
            [str(value) for value in relationship.GetTargets()]
            if relationship
            else []
        ),
        "binding_strength": (
            str(relationship.GetMetadata("bindMaterialAs"))
            if relationship
            else None
        ),
        "values": values,
        "physx_material_api_applied": bool(physx),
        "all_solver_attributes": generic,
    }


def _runtime_authority_methods(simulation_interface: Any) -> dict[str, Any]:
    requirements = {
        "live_solver_pair_materials": (
            "get_effective_contact_pair_material",
            "get_contact_pair_material",
        ),
        "contact_cache_and_warm_start": (
            "get_contact_pair_solver_cache",
            "get_contact_cache",
        ),
        "collision_eligible_pair_matrix": (
            "get_collision_pair_table",
            "get_collision_pairs",
        ),
    }
    selected = {}
    missing = []
    for requirement, candidates in requirements.items():
        available = [
            name
            for name in candidates
            if callable(getattr(simulation_interface, name, None))
        ]
        selected[requirement] = available
        if not available:
            missing.append(requirement)
    return {
        "required_candidate_methods": {
            key: list(value) for key, value in requirements.items()
        },
        "available_methods": selected,
        "missing_authorities": missing,
        "complete": not missing,
    }


def _require_runtime_authority(simulation_interface: Any) -> dict[str, Any]:
    authority = _runtime_authority_methods(simulation_interface)
    if not authority["complete"]:
        raise ProtocolBlocker(
            "required_live_physx_authority_unavailable",
            json.dumps(authority["missing_authorities"], sort_keys=True),
            evidence=authority,
        )
    return authority


def _invoke_pair_authority(
    simulation_interface: Any,
    methods: Sequence[str],
    *,
    stage_id: int,
    collider0: str,
    collider1: str,
) -> dict[str, Any]:
    attempts = []
    for name in methods:
        method = getattr(simulation_interface, name)
        for arguments in (
            (stage_id, collider0, collider1),
            (collider0, collider1),
        ):
            try:
                value = method(*arguments)
                native = _json_native(value)
                if isinstance(native, Mapping):
                    return {
                        "method": name,
                        "arguments": list(arguments),
                        "value": dict(native),
                    }
                attempts.append(
                    {
                        "method": name,
                        "argument_count": len(arguments),
                        "result_type": type(value).__name__,
                    }
                )
            except Exception as exc:
                attempts.append(
                    {
                        "method": name,
                        "argument_count": len(arguments),
                        "error": f"{type(exc).__name__}:{exc}",
                    }
                )
    raise ProtocolBlocker(
        "live_pair_authority_call_unsupported",
        json.dumps(attempts, sort_keys=True),
        evidence=attempts,
    )


def _runtime_define_zero_friction_material(
    stage: Any,
    *,
    layer: Any,
    material_path: str,
    finger_colliders: Sequence[str],
    baseline_bindings: Sequence[Mapping[str, Any]],
    source_binding: Mapping[str, Any],
) -> dict[str, Any]:
    from pxr import PhysxSchema, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade

    if not baseline_bindings or any(
        binding.get("values") != baseline_bindings[0].get("values")
        or binding.get("all_solver_attributes")
        != baseline_bindings[0].get("all_solver_attributes")
        for binding in baseline_bindings[1:]
    ):
        raise ProtocolBlocker(
            "finger_baseline_material_tuple_mismatch",
            "enabled finger colliders do not share one complete material tuple",
        )
    previous = stage.GetEditTarget()
    edits = []
    modes = ("average", "min", "multiply", "max")
    source_mode = source_binding.get("all_solver_attributes", {}).get(
        "physxMaterial:frictionCombineMode"
    )
    if source_mode not in modes:
        raise ProtocolBlocker(
            "source_friction_combine_authority_missing", str(source_mode)
        )
    zero_modes = [
        mode
        for mode in ("min", "multiply")
        if modes.index(mode) >= modes.index(source_mode)
    ]
    if not zero_modes:
        raise ProtocolBlocker(
            "finger_only_zero_friction_combine_impossible",
            f"source_mode={source_mode}",
        )
    selected_friction_mode = zero_modes[0]
    try:
        stage.SetEditTarget(Usd.EditTarget(layer))
        parent_path = str(Path(material_path).parent)
        if parent_path != "/" and not stage.GetPrimAtPath(parent_path):
            UsdGeom.Scope.Define(stage, parent_path)
        material = UsdShade.Material.Define(stage, material_path)
        material_api = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
        baseline = baseline_bindings[0]
        values = baseline["values"]
        material_api.CreateStaticFrictionAttr().Set(0.0)
        material_api.CreateDynamicFrictionAttr().Set(0.0)
        if values.get("restitution") is not None:
            material_api.CreateRestitutionAttr().Set(values["restitution"])
        if values.get("density") is not None:
            material_api.CreateDensityAttr().Set(values["density"])
        physx = PhysxSchema.PhysxMaterialAPI.Apply(material.GetPrim())
        baseline_attributes = baseline["all_solver_attributes"]
        for name, value in baseline_attributes.items():
            if name in {
                "physics:staticFriction",
                "physics:dynamicFriction",
                "physics:restitution",
                "physics:density",
            }:
                continue
            source_material = stage.GetPrimAtPath(baseline["material_path"])
            source_attribute = source_material.GetAttribute(name)
            if source_attribute and source_attribute.GetTypeName():
                target = material.GetPrim().CreateAttribute(
                    name, source_attribute.GetTypeName(), custom=False
                )
                target.Set(value)
        friction_mode = material.GetPrim().GetAttribute(
            "physxMaterial:frictionCombineMode"
        )
        if not friction_mode:
            friction_mode = material.GetPrim().CreateAttribute(
                "physxMaterial:frictionCombineMode",
                Sdf.ValueTypeNames.Token,
                custom=False,
            )
        friction_mode.Set(selected_friction_mode)
        for collider_path in finger_colliders:
            collider = stage.GetPrimAtPath(collider_path)
            binding = UsdShade.MaterialBindingAPI.Apply(collider)
            binding.Bind(
                material,
                UsdShade.Tokens.strongerThanDescendants,
                "physics",
            )
            edits.append(
                {
                    "collider_path": collider_path,
                    "material_path": material_path,
                    "strength": "strongerThanDescendants",
                    "purpose": "physics",
                }
            )
    finally:
        stage.SetEditTarget(previous)
    return {
        "material_path": material_path,
        "bindings": edits,
        "source_friction_combine_mode": source_mode,
        "selected_friction_combine_mode": selected_friction_mode,
        "physx_material_api_applied": bool(physx),
        "layer_sha256": _sha256_bytes(layer.ExportToString().encode("utf-8")),
    }


def _runtime_scene_identity(
    stage: Any, world: Any, *, expected_scene_paths: Sequence[str]
) -> dict[str, Any]:
    from pxr import Usd, UsdPhysics

    scene_paths = [
        str(prim.GetPath())
        for prim in Usd.PrimRange.Stage(stage)
        if prim.IsA(UsdPhysics.Scene)
    ]
    context = world.get_physics_context()
    context_path = getattr(context, "prim_path", None)
    context_path = context_path() if callable(context_path) else context_path
    context_path = str(context_path)
    dt = float(world.get_physics_dt())
    scene = UsdPhysics.Scene(stage.GetPrimAtPath(context_path))
    direction = np.asarray(scene.GetGravityDirectionAttr().Get(), dtype=np.float64)
    magnitude = float(scene.GetGravityMagnitudeAttr().Get())
    gravity = direction * magnitude
    valid = bool(
        scene_paths == list(expected_scene_paths)
        and context_path == "/physicsScene"
        and math.isclose(dt, 1.0 / 60.0, rel_tol=0.0, abs_tol=1.0e-12)
        and np.allclose(
            gravity,
            [0.0, 0.0, -9.81],
            rtol=0.0,
            atol=1.0e-6,
        )
    )
    return {
        "physics_scene_paths_in_traversal_order": scene_paths,
        "physics_context_path": context_path,
        "physics_dt": dt,
        "gravity_world_m_s2": gravity.tolist(),
        "valid": valid,
    }


def _runtime_dependency_closure(entry_path: Path) -> dict[str, Any]:
    from pxr import UsdUtils

    layers, assets, unresolved = UsdUtils.ComputeAllDependencies(str(entry_path))
    paths = {entry_path.resolve()}
    unresolved_values = [str(value) for value in unresolved]
    for value in (*layers, *assets):
        raw = str(
            getattr(value, "realPath", "")
            or getattr(value, "resolvedPath", "")
            or getattr(value, "path", "")
            or getattr(value, "identifier", "")
            or value
        )
        if not raw or raw.startswith("anon:") or "://" in raw:
            unresolved_values.append(raw)
            continue
        path = Path(raw)
        if not path.is_absolute():
            path = entry_path.parent / path
        path = path.resolve()
        if path.is_file():
            paths.add(path)
        else:
            unresolved_values.append(str(path))
    records = [
        {
            "path": str(path),
            "byte_count": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(paths, key=str)
    ]
    payload = {
        "entry_path": str(entry_path.resolve()),
        "files": records,
        "unresolved": sorted(set(unresolved_values)),
    }
    return {**payload, "sha256": _canonical_json_sha256(payload)}


def _runtime_mass_properties(
    app: Any, stage: Any, body_path: str
) -> dict[str, Any]:
    from omni.physx import get_physx_property_query_interface
    from omni.physx.bindings._physx import (
        PhysxPropertyQueryMode,
        PhysxPropertyQueryResult,
    )
    from pxr import PhysicsSchemaTools, UsdUtils

    prim = stage.GetPrimAtPath(body_path)
    if not prim or not prim.IsValid():
        raise ProtocolBlocker("source_mass_query_prim_missing", body_path)
    result: dict[str, Any] = {}
    finished = {"value": False}

    def rigid_body_callback(info: Any) -> None:
        if info.result != PhysxPropertyQueryResult.VALID:
            result["error"] = str(info.result)
            return
        result.update(
            {
                "mass_kg": float(info.mass),
                "center_of_mass_local_m": [
                    float(value) for value in info.center_of_mass
                ],
                "diagonal_inertia_kg_m2": [
                    float(value) for value in info.inertia
                ],
            }
        )

    get_physx_property_query_interface().query_prim(
        stage_id=UsdUtils.StageCache.Get().Insert(stage).ToLongInt(),
        prim_id=PhysicsSchemaTools.sdfPathToInt(prim.GetPath()),
        query_mode=PhysxPropertyQueryMode.QUERY_RIGID_BODY_ONLY,
        rigid_body_fn=rigid_body_callback,
        finished_fn=lambda: finished.__setitem__("value", True),
        timeout_ms=60000,
    )
    for _ in range(600):
        if finished["value"]:
            break
        app.update()
    if (
        not finished["value"]
        or "error" in result
        or set(result)
        != {
            "mass_kg",
            "center_of_mass_local_m",
            "diagonal_inertia_kg_m2",
        }
    ):
        raise ProtocolBlocker(
            "source_live_mass_authority_unavailable",
            json.dumps(result, sort_keys=True),
        )
    if not math.isclose(
        result["mass_kg"],
        0.019999999552965164,
        rel_tol=0.0,
        abs_tol=1.0e-9,
    ):
        raise ProtocolBlocker(
            "source_live_mass_mismatch", json.dumps(result, sort_keys=True)
        )
    return result


def _runtime_source_state(
    source_body: Any,
    tool_body: Any,
    stage: Any,
    tool_path: str,
    *,
    source_com_local_m: Any,
) -> dict[str, Any]:
    position, orientation = source_body.get_world_pose()
    linear = source_body.get_linear_velocity()
    angular = source_body.get_angular_velocity()
    _finite_vector(position, field="runtime_source_position")
    com_local = _finite_vector(
        source_com_local_m, field="runtime_source_com_local"
    )
    source_world_matrix = _runtime_row_matrix(stage, "/World/beaker2/mesh")
    source_position = (np.append(com_local, 1.0) @ source_world_matrix)[:3]
    source_orientation = np.asarray(orientation, dtype=np.float64)
    if (
        source_orientation.shape != (4,)
        or not np.isfinite(source_orientation).all()
    ):
        raise ProtocolBlocker(
            "source_orientation_authority_invalid", str(orientation)
        )
    sleeping_getter = getattr(source_body, "is_sleeping", None)
    sleeping = sleeping_getter() if callable(sleeping_getter) else None
    if isinstance(sleeping, np.ndarray):
        sleeping = bool(sleeping.reshape(-1)[0]) if sleeping.size == 1 else None
    if type(sleeping) is not bool:
        raise ProtocolBlocker(
            "source_awake_authority_unavailable", type(sleeping).__name__
        )
    if sleeping:
        raise ProtocolBlocker("source_sleeping_during_accepted_interval", tool_path)
    tool_matrix = _runtime_row_matrix(stage, tool_path)
    hand_position, _hand_orientation = tool_body.get_world_pose()
    hand_position = _finite_vector(
        hand_position, field="runtime_hand_position"
    )
    hand_linear = _finite_vector(
        tool_body.get_linear_velocity(), field="runtime_hand_linear_velocity"
    )
    hand_angular = _finite_vector(
        tool_body.get_angular_velocity(), field="runtime_hand_angular_velocity"
    )
    tool_position = tool_matrix[3, :3]
    tool_linear = hand_linear + np.cross(
        hand_angular, tool_position - hand_position
    )
    return {
        "source_com_m": source_position.tolist(),
        "source_orientation_wxyz": source_orientation.tolist(),
        "source_linear_velocity_m_s": _finite_vector(
            linear, field="runtime_source_linear_velocity"
        ).tolist(),
        "source_angular_velocity_rad_s": _finite_vector(
            angular, field="runtime_source_angular_velocity"
        ).tolist(),
        "tool_position_m": tool_matrix[3, :3].tolist(),
        "tool_linear_velocity_m_s": tool_linear.tolist(),
        "tool_angular_velocity_rad_s": hand_angular.tolist(),
        "tool_world_matrix": tool_matrix.tolist(),
        "source_world_matrix": source_world_matrix.tolist(),
        "source_awake": True,
    }


def _runtime_compact_state(
    source_state: Mapping[str, Any],
    *,
    support_current: bool,
    joint_velocities_rad_s: Any,
) -> dict[str, Any]:
    linear = np.asarray(source_state["source_linear_velocity_m_s"], dtype=np.float64)
    angular = np.asarray(source_state["source_angular_velocity_rad_s"], dtype=np.float64)
    velocities = np.asarray(joint_velocities_rad_s, dtype=np.float64)
    aperture_rate = abs(float(velocities[7] + velocities[8])) if len(velocities) > 8 else math.nan
    return {
        "source_com_m": list(source_state["source_com_m"]),
        "source_linear_speed_m_s": float(np.linalg.norm(linear)),
        "source_angular_speed_degrees_s": math.degrees(float(np.linalg.norm(angular))),
        "finger_aperture_rate_m_s": aperture_rate,
        "support_current": bool(support_current),
    }


def _relative_pose_drift(
    reference_source_to_tool: np.ndarray,
    source_world: Any,
    tool_world: Any,
) -> tuple[float, float]:
    source = np.asarray(source_world, dtype=np.float64)
    tool = np.asarray(tool_world, dtype=np.float64)
    current = source @ np.linalg.inv(tool)
    delta = current @ np.linalg.inv(reference_source_to_tool)
    translation = float(np.linalg.norm(delta[3, :3]))
    rotation = delta[:3, :3]
    cosine = float(np.clip((np.trace(rotation) - 1.0) / 2.0, -1.0, 1.0))
    return translation, math.degrees(math.acos(cosine))


class _CompleteRuntimeReporter:
    """Normalize one full PhysX report while retaining zero-data LOST headers."""

    _EVENT_NAMES = {
        "CONTACT_FOUND": "FOUND",
        "CONTACT_PERSIST": "PERSIST",
        "CONTACT_LOST": "LOST",
    }
    _EVENT_VALUES = {0: "FOUND", 1: "LOST", 2: "PERSIST"}

    def __init__(
        self,
        *,
        get_full_contact_report: Callable[[], Any],
        resolve_path: Callable[[int], Any],
        expected_stage_id: int,
        provisional_background_pairs: Sequence[Sequence[str]],
    ) -> None:
        from utils.controlled_contact import FullContactReportAccumulator

        self._get = get_full_contact_report
        self._resolve = resolve_path
        self._accumulator = FullContactReportAccumulator(
            expected_stage_id=expected_stage_id,
            provisional_background_pairs=provisional_background_pairs,
        )
        self._read_count = 0

    def _path(self, value: Any) -> str:
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
            raise ProtocolBlocker(
                "contact_report_path_id_invalid", str(value)
            )
        path = str(self._resolve(int(value)))
        if not path:
            raise ProtocolBlocker(
                "contact_report_path_resolution_failed", str(value)
            )
        return path

    def _event(self, value: Any) -> str:
        name = getattr(value, "name", None)
        if name in self._EVENT_NAMES:
            return self._EVENT_NAMES[name]
        try:
            return self._EVENT_VALUES[int(value)]
        except (KeyError, TypeError, ValueError) as exc:
            raise ProtocolBlocker(
                "contact_report_event_semantics_unsupported", str(value)
            ) from exc

    @staticmethod
    def _vector(value: Any, field: str) -> list[float]:
        try:
            result = [float(item) for item in value]
        except (TypeError, ValueError) as exc:
            raise ProtocolBlocker(
                "contact_report_vector_invalid", field
            ) from exc
        if len(result) != 3 or not all(math.isfinite(item) for item in result):
            raise ProtocolBlocker("contact_report_vector_invalid", field)
        return result

    def sample(
        self, *, physics_index: int, allow_support_bootstrap: bool
    ) -> dict[str, Any]:
        raw = self._get()
        if not isinstance(raw, tuple) or len(raw) != 3:
            raise ProtocolBlocker(
                "contact_report_tuple_semantics_unsupported", type(raw).__name__
            )
        raw_headers, raw_contacts, raw_friction = raw
        headers = []
        contacts = []
        friction = []
        try:
            for value in raw_headers:
                headers.append(
                    {
                        "type": self._event(value.type),
                        "stage_id": int(value.stage_id),
                        "actor0": self._path(value.actor0),
                        "actor1": self._path(value.actor1),
                        "collider0": self._path(value.collider0),
                        "collider1": self._path(value.collider1),
                        "proto_index0": int(value.proto_index0),
                        "proto_index1": int(value.proto_index1),
                        "contact_data_offset": int(value.contact_data_offset),
                        "num_contact_data": int(value.num_contact_data),
                        "friction_anchors_offset": int(
                            value.friction_anchors_offset
                        ),
                        "num_friction_anchors_data": int(
                            value.num_friction_anchors_data
                        ),
                    }
                )
            for value in raw_contacts:
                contacts.append(
                    {
                        "position": self._vector(value.position, "position"),
                        "normal": self._vector(value.normal, "normal"),
                        "impulse": self._vector(value.impulse, "impulse"),
                        "separation": float(value.separation),
                        "face_index0": int(value.face_index0),
                        "face_index1": int(value.face_index1),
                        "material0": self._path(value.material0),
                        "material1": self._path(value.material1),
                    }
                )
            for value in raw_friction:
                friction.append(
                    {
                        "position": self._vector(
                            value.position, "friction_position"
                        ),
                        "impulse": self._vector(
                            value.impulse, "friction_impulse"
                        ),
                    }
                )
        except AttributeError as exc:
            raise ProtocolBlocker(
                "contact_report_record_semantics_unsupported", str(exc)
            ) from exc
        normalized = self._accumulator.consume(
            physics_index=physics_index,
            headers=headers,
            contact_data=contacts,
            friction_anchors=friction,
            allow_provisional_persist_bootstrap=allow_support_bootstrap,
        )
        read_index = self._read_count
        self._read_count += 1
        return {
            **normalized,
            "authority": "probe_complete_physx_contact_report_v1",
            "immediate_read_index": read_index,
            "all_headers": headers,
            "all_contact_data": contacts,
            "all_friction_anchors": friction,
        }


def _runtime_orientation_calibration(
    *,
    stage: Any,
    world: Any,
    app: Any,
    single_rigid_prim_type: Any,
    simulation_interface: Any,
    resolve_path: Callable[[int], Any],
    stage_id: int,
) -> dict[str, Any]:
    from pxr import Gf, PhysxSchema, UsdGeom, UsdPhysics

    root = "/__OriginalEmptyContactLiftOrientationCalibration"
    floor_path = root + "/floor"
    body_path = root + "/falling"
    if stage.GetPrimAtPath(root).IsValid():
        raise ProtocolBlocker(
            "orientation_calibration_path_collision", root
        )
    UsdGeom.Xform.Define(stage, root)
    floor = UsdGeom.Cube.Define(stage, floor_path)
    floor.CreateSizeAttr(0.2)
    floor.AddTranslateOp().Set(Gf.Vec3d(100.0, 0.0, 0.0))
    UsdPhysics.CollisionAPI.Apply(floor.GetPrim())
    body = UsdGeom.Cube.Define(stage, body_path)
    body.CreateSizeAttr(0.05)
    body.AddTranslateOp().Set(Gf.Vec3d(100.0, 0.0, 0.20))
    UsdPhysics.CollisionAPI.Apply(body.GetPrim())
    UsdPhysics.RigidBodyAPI.Apply(body.GetPrim())
    mass = UsdPhysics.MassAPI.Apply(body.GetPrim())
    mass.CreateMassAttr().Set(1.0)
    report_api = PhysxSchema.PhysxContactReportAPI.Apply(body.GetPrim())
    report_api.CreateThresholdAttr().Set(0.0)
    report_api.CreateReportPairsRel().SetTargets([])
    setup = {
        "root": root,
        "floor_path": floor_path,
        "falling_body_path": body_path,
        "floor_size_m": 0.2,
        "falling_size_m": 0.05,
        "falling_mass_kg": 1.0,
        "falling_initial_position_m": [100.0, 0.0, 0.20],
        "physics_dt": 1.0 / 60.0,
    }
    setup_sha256 = _canonical_json_sha256(setup)
    reporter = _CompleteRuntimeReporter(
        get_full_contact_report=simulation_interface.get_full_contact_report,
        resolve_path=resolve_path,
        expected_stage_id=stage_id,
        provisional_background_pairs=(),
    )
    rigid = single_rigid_prim_type(
        prim_path=body_path,
        name="original_empty_contact_lift_orientation_calibration_body",
    )
    try:
        world.reset()
        rigid.initialize()
        accepted = None
        velocity_before = None
        velocity_after = None
        for local_index in range(180):
            velocity_before = _finite_vector(
                rigid.get_linear_velocity(),
                field="orientation_calibration_velocity",
            )
            world.step(render=False)
            velocity_after = _finite_vector(
                rigid.get_linear_velocity(),
                field="orientation_calibration_velocity",
            )
            report = reporter.sample(
                physics_index=local_index,
                allow_support_bootstrap=False,
            )
            for occurrence in report["occurrences"]:
                pair = _occurrence_pair(occurrence)
                if set(pair) == {floor_path, body_path}:
                    accepted = (occurrence, velocity_before, velocity_after)
                    break
            if accepted is not None:
                break
        if accepted is None:
            raise ProtocolBlocker(
                "orientation_calibration_contact_missing",
                f"setup_sha256={setup_sha256}",
            )
        occurrence, velocity_before, velocity_after = accepted
        fragment = occurrence["fragments"][0]
        header = fragment["header"]
        if not fragment["contact_data"]:
            raise ProtocolBlocker(
                "orientation_calibration_contact_data_missing", setup_sha256
            )
        point = fragment["contact_data"][0]
        normal = _finite_vector(
            point["normal"], field="orientation_calibration_normal", unit=True
        )
        impulse = _finite_vector(
            point["impulse"], field="orientation_calibration_impulse"
        )
        centers = {
            floor_path: _runtime_row_matrix(stage, floor_path)[3, :3],
            body_path: _runtime_row_matrix(stage, body_path)[3, :3],
        }
        collider0 = header["collider0"]
        collider1 = header["collider1"]
        center_direction = centers[collider1] - centers[collider0]
        center_direction /= np.linalg.norm(center_direction)
        direction_dot = float(normal @ center_direction)
        if abs(direction_dot) < 0.9:
            raise ProtocolBlocker(
                "orientation_calibration_normal_ambiguous",
                f"dot={direction_dot}",
            )
        normal_direction = (
            "collider0_to_collider1"
            if direction_dot > 0.0
            else "collider1_to_collider0"
        )
        upward = np.asarray([0.0, 0.0, 1.0], dtype=np.float64)
        impulse_up = float(impulse @ upward)
        if abs(impulse_up) <= 1.0e-12:
            raise ProtocolBlocker(
                "orientation_calibration_impulse_ambiguous",
                f"impulse={impulse.tolist()}",
            )
        dynamic_index = 0 if collider0 == body_path else 1
        raw_actor_index = dynamic_index if impulse_up > 0.0 else 1 - dynamic_index
        impulse_actor = "collider0" if raw_actor_index == 0 else "collider1"
        if float(velocity_after[2] - velocity_before[2]) <= -9.81 / 60.0:
            raise ProtocolBlocker(
                "orientation_calibration_momentum_not_observed",
                f"before={velocity_before.tolist()}:after={velocity_after.tolist()}",
            )
        return {
            "authority": "pinned_falling_cube_integration_v1",
            "setup": setup,
            "setup_sha256": setup_sha256,
            "normal_direction": normal_direction,
            "impulse_actor": impulse_actor,
            "header": header,
            "raw_normal": normal.tolist(),
            "raw_impulse_n_s": impulse.tolist(),
            "velocity_before_m_s": velocity_before.tolist(),
            "velocity_after_m_s": velocity_after.tolist(),
        }
    finally:
        stage.RemovePrim(root)
        app.update()
        world.reset()
        if stage.GetPrimAtPath(root).IsValid():
            raise ProtocolBlocker(
                "orientation_calibration_cleanup_failed", root
            )


def _runtime_stage_audit_snapshot(stage: Any) -> dict[str, Any]:
    from pxr import Usd, UsdPhysics

    monitored_roots = (
        "/World/beaker2",
        "/World/Franka",
    )
    attributes = []
    relationships = []
    constraints = []
    groups = []
    for prim in Usd.PrimRange.Stage(stage):
        path = str(prim.GetPath())
        monitored = any(
            path == root or path.startswith(root + "/")
            for root in monitored_roots
        )
        if prim.IsA(UsdPhysics.Joint) or "Attachment" in prim.GetTypeName():
            targets = []
            for relationship in prim.GetRelationships():
                targets.extend(str(value) for value in relationship.GetTargets())
            if any(
                value == "/World/beaker2"
                or value.startswith("/World/beaker2/")
                for value in targets
            ):
                constraints.append(
                    {"path": path, "type": prim.GetTypeName(), "targets": sorted(targets)}
                )
        if prim.IsA(UsdPhysics.CollisionGroup):
            groups.append(
                {
                    "path": path,
                    "relationships": {
                        relationship.GetName(): sorted(
                            str(value) for value in relationship.GetTargets()
                        )
                        for relationship in prim.GetRelationships()
                    },
                }
            )
        if not monitored:
            continue
        for attribute in prim.GetAttributes():
            name = attribute.GetName()
            if (
                name.startswith("xformOp:")
                or name.startswith("physics:")
                or name.startswith("physx:")
                or name.startswith("physxRigidBody:")
                or name.startswith("physxForce:")
            ):
                attributes.append(
                    {
                        "path": path,
                        "name": name,
                        "value": _json_native(attribute.Get()),
                    }
                )
        for relationship in prim.GetRelationships():
            name = relationship.GetName()
            if (
                "filteredPairs" in name
                or "collision" in name.lower()
                or "attachment" in name.lower()
            ):
                relationships.append(
                    {
                        "path": path,
                        "name": name,
                        "targets": sorted(
                            str(value) for value in relationship.GetTargets()
                        ),
                    }
                )
    payload = {
        "attributes": sorted(
            attributes, key=lambda item: (item["path"], item["name"])
        ),
        "relationships": sorted(
            relationships, key=lambda item: (item["path"], item["name"])
        ),
        "constraints": sorted(constraints, key=lambda item: item["path"]),
        "collision_groups": sorted(groups, key=lambda item: item["path"]),
    }
    return {**payload, "sha256": _canonical_json_sha256(payload)}


class _RuntimeCallAudit:
    def __init__(self, *, source_paths: Sequence[str]) -> None:
        self.source_paths = tuple(source_paths)
        self.epoch_open = False
        self.reset_root_write_count = 0
        self.counts = {
            "root_body_pose_velocity_writers": 0,
            "kinematic_targets": 0,
            "forces_torques_impulses": 0,
            "force_fields": 0,
            "software_gripper_attachments": 0,
            "constraints_attachments": 0,
            "forward_filters": 0,
            "reverse_filters": 0,
            "collision_group_changes": 0,
            "raw_property_changes": 0,
        }
        self.coverage = {name: False for name in REQUIRED_AUDIT_SURFACES}
        self._patches: list[tuple[Any, str, Any]] = []
        self._baseline_stage_snapshot: Mapping[str, Any] | None = None

    def _path_in_call(self, args: Sequence[Any], kwargs: Mapping[str, Any]) -> str | None:
        for name in ("object_path", "prim_path", "path"):
            value = kwargs.get(name)
            if isinstance(value, str):
                return value
        for value in args:
            if isinstance(value, str) and value.startswith("/"):
                return value
        return None

    def patch(
        self,
        obj: Any,
        method_name: str,
        *,
        coverage_names: Sequence[str],
        count_name: str,
        source_scoped: bool,
    ) -> None:
        original = getattr(obj, method_name, None)
        if not callable(original):
            for name in coverage_names:
                self.coverage[name] = True
            return

        def audited(*args: Any, **kwargs: Any) -> Any:
            path = self._path_in_call(args, kwargs)
            relevant = not source_scoped or path in self.source_paths
            if relevant:
                if self.epoch_open:
                    self.counts[count_name] += 1
                elif path == self.source_paths[0]:
                    self.reset_root_write_count += 1
            return original(*args, **kwargs)

        try:
            setattr(obj, method_name, audited)
        except Exception as exc:
            raise ProtocolBlocker(
                "audit_surface_not_patchable",
                f"{type(obj).__name__}.{method_name}:{type(exc).__name__}:{exc}",
            ) from exc
        self._patches.append((obj, method_name, original))
        for name in coverage_names:
            self.coverage[name] = True

    def seal_stage_baseline(self, stage: Any) -> None:
        self._baseline_stage_snapshot = _runtime_stage_audit_snapshot(stage)
        for name in (
            "raw_source_properties",
            "usd_runtime_constraints_attachments",
            "forward_filtered_pairs",
            "reverse_filtered_pairs",
            "collision_groups_masks_merge_groups",
            "physx_force_api",
            "force_field_membership",
        ):
            self.coverage[name] = True

    def check_stage(self, stage: Any) -> None:
        current = _runtime_stage_audit_snapshot(stage)
        if self._baseline_stage_snapshot is None:
            raise ProtocolBlocker(
                "audit_stage_baseline_missing", "seal_stage_baseline not called"
            )
        if current["sha256"] != self._baseline_stage_snapshot["sha256"]:
            self.counts["raw_property_changes"] += 1

    def open_epoch(self) -> None:
        self.epoch_open = True

    def close(self) -> None:
        for obj, name, original in reversed(self._patches):
            try:
                setattr(obj, name, original)
            except Exception:
                pass
        self._patches.clear()

    def report(self) -> dict[str, Any]:
        return {
            "coverage": dict(self.coverage),
            "post_reset_counts": dict(self.counts),
            "reset_root_write_count": self.reset_root_write_count,
            "zero_write_epoch_opened": self.epoch_open,
        }


def _runtime_pair_key(first: str, second: str) -> frozenset[str]:
    return frozenset((first, second))


def _runtime_contact_evidence(
    report: Mapping[str, Any] | None,
    *,
    geometry: Mapping[str, Any] | None,
    source_collider: str,
    support_collider: str,
    target_pairs: Mapping[frozenset[str], str],
    orientation: Mapping[str, Any] | None,
    aperture_rate_m_s: float,
) -> dict[str, Any]:
    default = {
        "bilateral_qualified": False,
        "prohibited_contact": False,
        "source_tool_drift_translation_m": 0.0,
        "source_tool_drift_rotation_degrees": 0.0,
        "left_friction_anchor_norm_n_s": 0.0,
        "right_friction_anchor_norm_n_s": 0.0,
        "support_event": None,
        "support_contact_count": 0,
        "support_friction_anchor_count": 0,
        "support_impulse_n_s": 0.0,
        "support_current": False,
        "geometry": None,
        "reduced_occurrences": [],
        "raw_report": copy.deepcopy(report),
    }
    if report is None:
        return default
    if geometry is None or orientation is None:
        raise ProtocolBlocker(
            "instrumented_contact_authority_missing",
            "geometry or orientation calibration absent",
        )
    current_pairs = {
        frozenset(item["collider_path"] for item in pair)
        for pair in report.get("current_pairs", [])
    }
    support_pair = _runtime_pair_key(source_collider, support_collider)
    reduced_target = []
    reduced_all = []
    prohibited = False
    support_reduced = None
    for occurrence in report.get("occurrences", []):
        pair = frozenset(_occurrence_pair(occurrence))
        if source_collider in pair:
            reduced = reduce_contact_occurrence(
                occurrence,
                source_collider=source_collider,
                impulse_actor=str(orientation["impulse_actor"]),
                normal_direction=str(orientation["normal_direction"]),
            )
            reduced_all.append(reduced)
            if pair in target_pairs:
                reduced["finger_collider"] = reduced["other_collider"]
                reduced_target.append(reduced)
            elif pair == support_pair:
                support_reduced = reduced
            else:
                prohibited = True
        else:
            paths = set(pair)
            robot_contact = any(path.startswith("/World/Franka") for path in paths)
            environment_contact = any(
                not path.startswith("/World/Franka") for path in paths
            )
            if robot_contact and environment_contact:
                prohibited = True
    geometry_result = evaluate_bilateral_geometry(
        reduced_target,
        geometry=geometry,
        finger_aperture_rate_m_s=aperture_rate_m_s,
    )
    if not geometry_result["protocol_valid"]:
        raise ProtocolBlocker(
            "contact_geometry_authority_invalid",
            json.dumps(geometry_result["protocol_failures"], sort_keys=True),
            evidence=geometry_result,
        )
    side_friction = {"left": 0.0, "right": 0.0}
    for reduced in reduced_target:
        side = target_pairs[
            _runtime_pair_key(source_collider, reduced["finger_collider"])
        ]
        side_friction[side] += float(reduced["friction_anchor_norm_n_s"])
    support_headers = [
        header
        for header in report.get("all_headers", [])
        if _runtime_pair_key(header.get("collider0"), header.get("collider1"))
        == support_pair
    ]
    support_events = [header["type"] for header in support_headers]
    support_event = ",".join(
        event for index, event in enumerate(support_events) if index == 0 or event != support_events[index - 1]
    ) or None
    if support_event == "LOST":
        if any(
            header["num_contact_data"] != 0
            or header["num_friction_anchors_data"] != 0
            for header in support_headers
        ):
            raise ProtocolBlocker(
                "support_lost_nonzero_records", json.dumps(support_headers)
            )
    return {
        **default,
        "bilateral_qualified": geometry_result["qualified"],
        "prohibited_contact": prohibited,
        "left_friction_anchor_norm_n_s": side_friction["left"],
        "right_friction_anchor_norm_n_s": side_friction["right"],
        "support_event": support_event,
        "support_contact_count": (
            len(support_reduced["points"]) if support_reduced else 0
        ),
        "support_friction_anchor_count": (
            len(support_reduced["friction_anchors"])
            if support_reduced
            else 0
        ),
        "support_impulse_n_s": (
            float(support_reduced["normal_impulse_n_s"])
            if support_reduced
            else 0.0
        ),
        "support_current": support_pair in current_pairs,
        "geometry": geometry_result,
        "reduced_occurrences": reduced_all,
    }


def _runtime_comparison_sample(
    *,
    controller_event: int | None,
    source_state: Mapping[str, Any],
    robot: Any,
    contact: Mapping[str, Any],
) -> dict[str, Any]:
    from scipy.spatial.transform import Rotation

    tool_matrix = np.asarray(source_state["tool_world_matrix"], dtype=np.float64)
    tool_xyzw = Rotation.from_matrix(tool_matrix[:3, :3].T).as_quat()
    source_linear = np.asarray(
        source_state["source_linear_velocity_m_s"], dtype=np.float64
    )
    source_angular = np.asarray(
        source_state["source_angular_velocity_rad_s"], dtype=np.float64
    )
    predicate_margins = {}
    geometry = contact.get("geometry")
    if isinstance(geometry, Mapping):
        for point_index, point in enumerate(geometry.get("points", [])):
            for name, value in point.get("margins", {}).items():
                predicate_margins[
                    f"{point_index}:{point.get('side')}:{name}"
                ] = float(value)
    return {
        "controller_event": controller_event,
        "joint_positions_rad": np.asarray(
            robot.get_joint_positions(), dtype=np.float64
        ).tolist(),
        "tool_position_m": tool_matrix[3, :3].tolist(),
        "tool_orientation_wxyz": tool_xyzw[[3, 0, 1, 2]].tolist(),
        "source_position_m": list(source_state["source_com_m"]),
        "source_orientation_wxyz": list(
            source_state["source_orientation_wxyz"]
        ),
        "tool_linear_velocity_m_s": list(
            source_state["tool_linear_velocity_m_s"]
        ),
        "tool_angular_velocity_rad_s": list(
            source_state["tool_angular_velocity_rad_s"]
        ),
        "source_linear_velocity_m_s": source_linear.tolist(),
        "source_angular_velocity_rad_s": source_angular.tolist(),
        "predicate_margins": predicate_margins,
    }


def _runtime_execute_trajectory(
    *,
    world: Any,
    task: Any,
    controller: Any,
    robot: Any,
    source_body: Any,
    tool_body: Any,
    source_com_local_m: Any,
    stage: Any,
    reporter: _CompleteRuntimeReporter | None,
    geometry: Mapping[str, Any] | None,
    source_collider: str,
    support_collider: str,
    target_pairs: Mapping[frozenset[str], str],
    orientation: Mapping[str, Any] | None,
    audit: _RuntimeCallAudit,
    maximum_steps: int,
    retention_steps: int,
    requested_pose_sha256: str,
    readback_pose_sha256: str,
    config_sha256: str,
) -> dict[str, Any]:
    transitions = []
    controller_events = []
    action_hashes = []
    samples = []
    continuation_samples = []
    continuation_world_indices = []
    common_contact_stream = []
    pending_receipt = None
    reference_source_to_tool = None
    pre_source = _runtime_source_state(
        source_body,
        tool_body,
        stage,
        "/World/Franka/panda_hand/tool_center",
        source_com_local_m=source_com_local_m,
    )
    pre_joint_positions = np.asarray(
        robot.get_joint_positions(), dtype=np.float64
    )
    pre_joint_velocities = np.asarray(
        robot.get_joint_velocities(), dtype=np.float64
    )
    if (
        pre_joint_positions.ndim != 1
        or pre_joint_velocities.shape != pre_joint_positions.shape
        or len(pre_joint_positions) <= 8
        or not np.isfinite(pre_joint_positions).all()
        or not np.isfinite(pre_joint_velocities).all()
    ):
        raise ProtocolBlocker(
            "robot_joint_state_authority_invalid",
            f"positions={pre_joint_positions.shape}:velocities={pre_joint_velocities.shape}",
        )
    prior_support = True
    terminal_outcome = None
    terminal_phase = None
    terminal_world_index = None

    for transition_index in range(maximum_steps):
        before_world = _runtime_world_counter(world)
        world.step(render=True)
        after_world = _runtime_world_counter(world)
        if after_world != before_world + 1:
            raise ProtocolBlocker(
                "world_step_advance_invalid",
                f"before={before_world}:after={after_world}",
            )
        report = (
            reporter.sample(
                physics_index=transition_index,
                allow_support_bootstrap=transition_index == 0,
            )
            if reporter is not None
            else None
        )
        post_source = _runtime_source_state(
            source_body,
            tool_body,
            stage,
            "/World/Franka/panda_hand/tool_center",
            source_com_local_m=source_com_local_m,
        )
        post_joint_positions = np.asarray(
            robot.get_joint_positions(), dtype=np.float64
        )
        joint_velocities = np.asarray(
            robot.get_joint_velocities(), dtype=np.float64
        )
        if (
            post_joint_positions.shape != pre_joint_positions.shape
            or joint_velocities.shape != pre_joint_velocities.shape
            or not np.isfinite(post_joint_positions).all()
            or not np.isfinite(joint_velocities).all()
        ):
            raise ProtocolBlocker(
                "finger_joint_velocity_authority_invalid",
                str(joint_velocities.shape),
            )
        aperture_rate = abs(
            float(joint_velocities[7] + joint_velocities[8])
        )
        contact = _runtime_contact_evidence(
            report,
            geometry=geometry,
            source_collider=source_collider,
            support_collider=support_collider,
            target_pairs=target_pairs,
            orientation=orientation,
            aperture_rate_m_s=aperture_rate,
        )
        if reporter is None:
            contact["support_current"] = prior_support
        if pending_receipt and pending_receipt.get("native_event") == 5:
            if reference_source_to_tool is not None:
                raise ProtocolBlocker(
                    "multiple_lift_actions_observed", str(transition_index)
                )
            reference_source_to_tool = np.asarray(
                pre_source["source_world_matrix"], dtype=np.float64
            ) @ np.linalg.inv(
                np.asarray(pre_source["tool_world_matrix"], dtype=np.float64)
            )
        if reference_source_to_tool is not None:
            drift_translation, drift_rotation = _relative_pose_drift(
                reference_source_to_tool,
                post_source["source_world_matrix"],
                post_source["tool_world_matrix"],
            )
            contact["source_tool_drift_translation_m"] = drift_translation
            contact["source_tool_drift_rotation_degrees"] = drift_rotation

        phase_before = str(getattr(controller.current_phase, "name", "UNKNOWN"))
        state = task.step()
        controller_call_count = 0
        action = None
        done = False
        success = False
        event = None
        if state is not None:
            controller_call_count = 1
            result = controller.step(state)
            if not isinstance(result, tuple) or len(result) != 3:
                raise ProtocolBlocker(
                    "controller_return_contract_invalid", type(result).__name__
                )
            action, done, success = result
            if type(done) is not bool or type(success) is not bool:
                raise ProtocolBlocker(
                    "controller_return_flags_invalid", str(result[1:])
                )
            pick = getattr(controller, "pick_controller", None)
            event = getattr(pick, "_last_emitted_event", None)
            if event is not None:
                if type(event) is not int or not 0 <= event <= 6:
                    raise ProtocolBlocker(
                        "native_pick_event_invalid", str(event)
                    )
                controller_events.append(event)
        phase_after = str(getattr(controller.current_phase, "name", "UNKNOWN"))
        canonical_action = None
        raw_action = None
        apply_count = 0
        current_receipt = None
        if action is not None:
            if phase_before == "POURING":
                raise ProtocolBlocker(
                    "pour_action_emitted", str(transition_index)
                )
            raw_action = raw_action_channels(action)
            canonical_action = canonicalize_action(raw_action)
            action_hashes.append(canonical_action["sha256"])
            apply_count = 1
            robot.get_articulation_controller().apply_action(action)
            current_receipt = {
                "native_event": event,
                "applied": True,
                "normal_return": True,
                "apply_count": 1,
                "action_sha256": canonical_action["sha256"],
            }
        production_terminal = False
        if phase_before == "PICKING" and phase_after == "POURING":
            if action is not None or done or success:
                raise ProtocolBlocker(
                    "pouring_transition_contract_invalid",
                    f"action={action is not None}:done={done}:success={success}",
                )
            production_terminal = True
            terminal_outcome = "POURING"
        elif done:
            if success or action is not None or phase_before != "PICKING":
                raise ProtocolBlocker(
                    "pick_terminal_contract_invalid",
                    f"phase={phase_before}:action={action is not None}:success={success}",
                )
            production_terminal = True
            terminal_outcome = "PICKING_FAILURE"
        if world.is_stopped() or task.need_reset() or controller.need_reset():
            raise ProtocolBlocker(
                "unexpected_world_or_reset_request",
                f"world_stopped={world.is_stopped()}:task_reset={task.need_reset()}:controller_reset={controller.need_reset()}",
            )
        pre_compact = _runtime_compact_state(
            pre_source,
            support_current=prior_support,
            joint_velocities_rad_s=pre_joint_velocities,
        )
        post_compact = _runtime_compact_state(
            post_source,
            support_current=bool(contact["support_current"]),
            joint_velocities_rad_s=joint_velocities,
        )
        payload = {
            "transition_index": transition_index,
            "world_index": after_world,
            "pre": pre_compact,
            "post": post_compact,
            "authority_pre": copy.deepcopy(pre_source),
            "authority_post": copy.deepcopy(post_source),
            "robot_pre": {
                "joint_positions_rad": pre_joint_positions.tolist(),
                "joint_velocities_rad_s": pre_joint_velocities.tolist(),
            },
            "robot_post": {
                "joint_positions_rad": post_joint_positions.tolist(),
                "joint_velocities_rad_s": joint_velocities.tolist(),
            },
            "phase_before": phase_before,
            "phase_after": phase_after,
            "action_receipt": pending_receipt,
            "contact": {
                key: copy.deepcopy(value)
                for key, value in contact.items()
                if key != "support_current"
            },
            "production_terminal": production_terminal,
            "terminal_outcome": terminal_outcome if production_terminal else None,
            "continuation_index": None,
            "controller_called": controller_call_count == 1,
            "new_action_applied": apply_count == 1,
            "controller_call_count": controller_call_count,
            "native_event": event,
            "canonical_action": canonical_action,
            "raw_action": raw_action,
            "apply_count": apply_count,
        }
        transitions.append(payload)
        if state is not None:
            samples.append(
                _runtime_comparison_sample(
                    controller_event=event,
                    source_state=post_source,
                    robot=robot,
                    contact=contact,
                )
            )
        audit.check_stage(stage)
        pending_receipt = current_receipt
        pre_source = post_source
        pre_joint_positions = post_joint_positions
        pre_joint_velocities = joint_velocities
        prior_support = bool(contact["support_current"])
        if production_terminal:
            terminal_phase = phase_after
            terminal_world_index = after_world
            if pending_receipt is not None:
                raise ProtocolBlocker(
                    "terminal_pending_action_invalid", str(pending_receipt)
                )
            break
    if terminal_outcome is None:
        raise ProtocolBlocker(
            "maximum_production_steps_exceeded", str(maximum_steps)
        )

    for continuation_index in range(retention_steps):
        transition_index = len(transitions)
        before_world = _runtime_world_counter(world)
        world.step(render=True)
        after_world = _runtime_world_counter(world)
        if after_world != before_world + 1:
            raise ProtocolBlocker(
                "continuation_world_step_invalid",
                f"before={before_world}:after={after_world}",
            )
        report = (
            reporter.sample(
                physics_index=transition_index,
                allow_support_bootstrap=False,
            )
            if reporter is not None
            else None
        )
        post_source = _runtime_source_state(
            source_body,
            tool_body,
            stage,
            "/World/Franka/panda_hand/tool_center",
            source_com_local_m=source_com_local_m,
        )
        post_joint_positions = np.asarray(
            robot.get_joint_positions(), dtype=np.float64
        )
        joint_velocities = np.asarray(
            robot.get_joint_velocities(), dtype=np.float64
        )
        if (
            post_joint_positions.shape != pre_joint_positions.shape
            or joint_velocities.shape != pre_joint_velocities.shape
            or not np.isfinite(post_joint_positions).all()
            or not np.isfinite(joint_velocities).all()
        ):
            raise ProtocolBlocker(
                "robot_joint_state_authority_invalid",
                f"positions={post_joint_positions.shape}:velocities={joint_velocities.shape}",
            )
        aperture_rate = abs(
            float(joint_velocities[7] + joint_velocities[8])
        )
        contact = _runtime_contact_evidence(
            report,
            geometry=geometry,
            source_collider=source_collider,
            support_collider=support_collider,
            target_pairs=target_pairs,
            orientation=orientation,
            aperture_rate_m_s=aperture_rate,
        )
        if reporter is None:
            contact["support_current"] = prior_support
        if reference_source_to_tool is not None:
            drift_translation, drift_rotation = _relative_pose_drift(
                reference_source_to_tool,
                post_source["source_world_matrix"],
                post_source["tool_world_matrix"],
            )
            contact["source_tool_drift_translation_m"] = drift_translation
            contact["source_tool_drift_rotation_degrees"] = drift_rotation
        payload = {
            "transition_index": transition_index,
            "world_index": after_world,
            "pre": _runtime_compact_state(
                pre_source,
                support_current=prior_support,
                joint_velocities_rad_s=pre_joint_velocities,
            ),
            "post": _runtime_compact_state(
                post_source,
                support_current=bool(contact["support_current"]),
                joint_velocities_rad_s=joint_velocities,
            ),
            "authority_pre": copy.deepcopy(pre_source),
            "authority_post": copy.deepcopy(post_source),
            "robot_pre": {
                "joint_positions_rad": pre_joint_positions.tolist(),
                "joint_velocities_rad_s": pre_joint_velocities.tolist(),
            },
            "robot_post": {
                "joint_positions_rad": post_joint_positions.tolist(),
                "joint_velocities_rad_s": joint_velocities.tolist(),
            },
            "phase_before": terminal_phase,
            "phase_after": terminal_phase,
            "action_receipt": None,
            "contact": {
                key: copy.deepcopy(value)
                for key, value in contact.items()
                if key != "support_current"
            },
            "production_terminal": False,
            "terminal_outcome": None,
            "continuation_index": continuation_index,
            "controller_called": False,
            "new_action_applied": False,
            "controller_call_count": 0,
            "native_event": None,
            "canonical_action": None,
            "raw_action": None,
            "apply_count": 0,
        }
        transitions.append(payload)
        continuation_samples.append(
            _runtime_comparison_sample(
                controller_event=None,
                source_state=post_source,
                robot=robot,
                contact=contact,
            )
        )
        continuation_world_indices.append(after_world)
        audit.check_stage(stage)
        pre_source = post_source
        pre_joint_positions = post_joint_positions
        pre_joint_velocities = joint_velocities
        prior_support = bool(contact["support_current"])

    comparison_summary = {
        "config_sha256": config_sha256,
        "requested_pose_sha256": requested_pose_sha256,
        "readback_pose_sha256": readback_pose_sha256,
        "reset_count": 2,
        "controller_events": controller_events,
        "action_sha256": action_hashes,
        "controller_outcome": terminal_outcome,
        "samples": samples,
        "continuation": continuation_samples,
        "continuation_world_indices": continuation_world_indices,
        "retention_passed": True,
        "common_contact_stream": common_contact_stream,
    }
    return {
        "transitions": transitions,
        "comparison_summary": comparison_summary,
        "terminal_outcome": terminal_outcome,
        "terminal_world_index": terminal_world_index,
    }


def _runtime_live_pair_table(
    *,
    simulation_interface: Any,
    authority: Mapping[str, Any],
    stage_id: int,
    finger_colliders: Sequence[str],
    all_colliders: Sequence[str],
    source_collider: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    available = authority.get("available_methods")
    if not isinstance(available, Mapping):
        raise ProtocolBlocker(
            "live_pair_authority_inventory_invalid", str(authority)
        )
    rows = []
    caches = {}
    for finger in sorted(finger_colliders):
        for counterpart in sorted(all_colliders):
            if counterpart == finger:
                continue
            eligibility = _invoke_pair_authority(
                simulation_interface,
                available["collision_eligible_pair_matrix"],
                stage_id=stage_id,
                collider0=finger,
                collider1=counterpart,
            )
            eligible = eligibility["value"].get("eligible")
            if type(eligible) is not bool:
                raise ProtocolBlocker(
                    "collision_pair_eligibility_authority_malformed",
                    f"{finger}|{counterpart}:{eligibility['value']}",
                )
            if not eligible:
                continue
            material = _invoke_pair_authority(
                simulation_interface,
                available["live_solver_pair_materials"],
                stage_id=stage_id,
                collider0=finger,
                collider1=counterpart,
            )
            cache = _invoke_pair_authority(
                simulation_interface,
                available["contact_cache_and_warm_start"],
                stage_id=stage_id,
                collider0=finger,
                collider1=counterpart,
            )
            value = material["value"]
            required = {
                "effective_static_friction",
                "effective_dynamic_friction",
                "effective_restitution",
                "selected_friction_combine",
                "selected_restitution_combine",
                "other_solver_terms_float32_hex",
            }
            if not required <= set(value):
                raise ProtocolBlocker(
                    "live_solver_material_authority_malformed",
                    f"{finger}|{counterpart}:missing={sorted(required-set(value))}",
                )
            pair_id = " | ".join(sorted((finger, counterpart)))
            rows.append(
                {
                    "pair_id": pair_id,
                    "eligible": True,
                    "target_pair": counterpart == source_collider,
                    "runtime_authority": "physx_live_solver_material_v1",
                    "selected_friction_combine": str(
                        value["selected_friction_combine"]
                    ),
                    "selected_restitution_combine": str(
                        value["selected_restitution_combine"]
                    ),
                    "effective_static_friction": float(
                        value["effective_static_friction"]
                    ),
                    "effective_dynamic_friction": float(
                        value["effective_dynamic_friction"]
                    ),
                    "effective_restitution": float(
                        value["effective_restitution"]
                    ),
                    "other_solver_terms_float32_hex": str(
                        value["other_solver_terms_float32_hex"]
                    ),
                }
            )
            caches[pair_id] = cache["value"]
    if not rows or not any(row["target_pair"] for row in rows):
        raise ProtocolBlocker(
            "live_target_pair_table_missing",
            f"finger_colliders={list(finger_colliders)}:source={source_collider}",
        )
    return rows, caches


def _runtime_source_contract(
    stage: Any,
    *,
    source_body_path: str,
    source_collider_path: str,
    support_path: str,
    finger_body_paths: Sequence[str],
) -> dict[str, Any]:
    from pxr import Usd, UsdPhysics

    source = stage.GetPrimAtPath(source_body_path)
    collider = stage.GetPrimAtPath(source_collider_path)
    if not source or not source.IsValid() or not collider or not collider.IsValid():
        raise ProtocolBlocker(
            "source_identity_missing",
            f"body={source_body_path}:collider={source_collider_path}",
        )
    rigid = UsdPhysics.RigidBodyAPI(source)
    collision = UsdPhysics.CollisionAPI(collider)
    mass_api = UsdPhysics.MassAPI(source)
    mass = mass_api.GetMassAttr().Get() if mass_api else None
    owners = {}
    for path in (source_body_path, source_collider_path, support_path, *finger_body_paths):
        prim = stage.GetPrimAtPath(path)
        relationship = prim.GetRelationship("physics:simulationOwner") if prim else None
        owners[path] = (
            [str(value) for value in relationship.GetTargets()]
            if relationship
            else []
        )
    record = {
        "source_body_path": source_body_path,
        "source_collider_path": source_collider_path,
        "mass_kg": float(mass) if mass is not None else None,
        "rigid_body_enabled": (
            rigid.GetRigidBodyEnabledAttr().Get() if rigid else None
        ),
        "kinematic_enabled": (
            rigid.GetKinematicEnabledAttr().Get() if rigid else None
        ),
        "collision_enabled": (
            collision.GetCollisionEnabledAttr().Get() if collision else None
        ),
        "disable_gravity": source.GetAttribute(
            "physxRigidBody:disableGravity"
        ).Get(),
        "simulation_owners": owners,
    }
    record["valid"] = bool(
        record["rigid_body_enabled"] is not False
        and record["kinematic_enabled"] is not True
        and record["collision_enabled"] is not False
        and record["disable_gravity"] is not True
        and record["mass_kg"] is not None
        and math.isclose(
            record["mass_kg"],
            0.019999999552965164,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        )
        and all(
            targets in ([], ["/physicsScene"])
            for targets in owners.values()
        )
        and all(
            "/World/PhysicsScene" not in targets
            for targets in owners.values()
        )
    )
    return record


def _runtime_all_enabled_colliders(stage: Any) -> list[str]:
    from pxr import Usd, UsdPhysics

    result = []
    for prim in Usd.PrimRange.Stage(stage):
        if not prim.HasAPI(UsdPhysics.CollisionAPI):
            continue
        enabled = UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()
        if enabled is not False:
            if prim.IsInstance() or prim.IsInstanceProxy():
                raise ProtocolBlocker(
                    "collision_instance_authority_unsupported", str(prim.GetPath())
                )
            result.append(str(prim.GetPath()))
    return sorted(result)


def _runtime_default_franka_identity(stage: Any) -> dict[str, Any]:
    from pxr import Usd

    prim = stage.GetPrimAtPath("/World/Franka")
    if not prim or not prim.IsValid():
        raise ProtocolBlocker("default_franka_root_missing", "/World/Franka")
    stack = prim.GetPrimStack()
    layers = []
    for spec in stack:
        layer = spec.layer
        identifier = str(layer.identifier)
        real_path = str(layer.realPath or "")
        record = {"identifier": identifier, "real_path": real_path}
        if real_path and Path(real_path).is_file():
            record["sha256"] = sha256_file(real_path)
        layers.append(record)
    if not any("FrankaPanda/franka.usd" in item["identifier"] for item in layers):
        raise ProtocolBlocker(
            "default_franka_resolution_invalid", json.dumps(layers, sort_keys=True)
        )
    return {
        "root_path": "/World/Franka",
        "prim_stack_layers": layers,
        "sha256": _canonical_json_sha256(layers),
    }


def _runtime_version_and_gpu_identity() -> dict[str, Any]:
    import carb.settings
    import omni.kit.app

    application = omni.kit.app.get_app()
    build = None
    for method_name in ("get_build_version", "get_version"):
        method = getattr(application, method_name, None)
        if callable(method):
            value = method()
            if value:
                build = str(value)
                break
    extension_manager = application.get_extension_manager()
    extensions = {}
    for extension_id in (
        "omni.physx",
        "omni.physx.bundle",
        "omni.physx.tensors",
        "omni.usd.schema.physx",
    ):
        try:
            enabled_id = extension_manager.get_enabled_extension_id(extension_id)
            metadata = (
                extension_manager.get_extension_dict(enabled_id)
                if enabled_id
                else None
            )
            extensions[extension_id] = {
                "enabled_id": str(enabled_id) if enabled_id else None,
                "version": (
                    str(metadata.get("package", {}).get("version"))
                    if isinstance(metadata, Mapping)
                    else None
                ),
            }
        except Exception as exc:
            extensions[extension_id] = {
                "error": f"{type(exc).__name__}:{exc}"
            }
    settings = carb.settings.get_settings()
    gpu_keys = (
        "/physics/cudaDevice",
        "/physics/suppressReadback",
        "/persistent/physics/useFastCache",
        "/physics/enableGPUDynamics",
        "/physics/broadphaseType",
    )
    gpu = {key: _json_native(settings.get(key)) for key in gpu_keys}
    payload = {
        "kit_build_version": build,
        "python_executable": str(Path(sys.executable).resolve()),
        "python_version": sys.version.split()[0],
        "numpy_version": np.__version__,
        "extensions": extensions,
        "gpu_settings": gpu,
    }
    return {**payload, "sha256": _canonical_json_sha256(payload)}


def _validate_treatment_tree(root: Path) -> dict[str, Any]:
    root = root.resolve()
    paths = []
    for path in sorted(root.rglob("*"), key=lambda value: str(value)):
        if path.is_symlink():
            raise ValueError(f"probe_treatment_symlink_forbidden:{path}")
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"probe_output_path_escape:{path}") from exc
        paths.append(relative.as_posix())
    return {
        "root": str(root),
        "path_count": len(paths),
        "paths": paths,
        "valid": True,
    }


def _runtime_prelift_parity_record(
    trajectory: Mapping[str, Any],
    *,
    solver_caches: Mapping[str, Any],
    pair_table: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    transitions = trajectory.get("transitions")
    if not isinstance(transitions, Sequence):
        raise ProtocolBlocker(
            "prelift_parity_trace_authority_missing", "transitions"
        )
    lift = next(
        (
            record
            for record in transitions
            if isinstance(record.get("action_receipt"), Mapping)
            and record["action_receipt"].get("native_event") == 5
        ),
        None,
    )
    if lift is None or not solver_caches:
        raise ProtocolBlocker(
            "prelift_parity_authority_missing",
            f"lift={lift is not None}:caches={bool(solver_caches)}",
        )
    robot_pre = lift.get("robot_pre")
    authority_pre = lift.get("authority_pre")
    if not isinstance(robot_pre, Mapping) or not isinstance(
        authority_pre, Mapping
    ):
        raise ProtocolBlocker(
            "prelift_state_authority_missing", str(lift["transition_index"])
        )
    joints = np.asarray(robot_pre["joint_positions_rad"], dtype=np.float64)
    joint_velocities = np.asarray(
        robot_pre["joint_velocities_rad_s"], dtype=np.float64
    )
    if (
        joints.ndim != 1
        or len(joints) <= 8
        or joint_velocities.shape != joints.shape
        or not np.isfinite(joints).all()
        or not np.isfinite(joint_velocities).all()
    ):
        raise ProtocolBlocker(
            "prelift_joint_authority_invalid", str(joints.shape)
        )
    contact = lift["contact"]
    geometry = contact.get("geometry")
    if not isinstance(geometry, Mapping):
        raise ProtocolBlocker(
            "prelift_geometry_authority_missing", str(lift["transition_index"])
        )
    source_inverse = np.linalg.inv(
        np.asarray(authority_pre["source_world_matrix"], dtype=np.float64)
    )
    side_points = {"left": [], "right": []}
    margins = {}
    for index, point in enumerate(geometry.get("points", [])):
        side = point.get("side")
        if side in side_points:
            local = (
                np.append(
                    np.asarray(point["position_world_m"], dtype=np.float64),
                    1.0,
                )
                @ source_inverse
            )[:3]
            side_points[side].append(local.tolist())
        for name, value in point.get("margins", {}).items():
            margins[f"{index}:{side}:{name}"] = float(value)
    support_points = []
    support_anchors = []
    support_point_records = []
    support_anchor_records = []
    support_normal_impulse = 0.0
    support_friction_norm = 0.0
    side_normal = {"left": 0.0, "right": 0.0}
    for occurrence in contact.get("reduced_occurrences", []):
        other = occurrence.get("other_collider")
        if other == "/World/Cube":
            support_points.extend(
                (
                    np.append(
                        np.asarray(point["position_world_m"], dtype=np.float64),
                        1.0,
                    )
                    @ source_inverse
                )[:3].tolist()
                for point in occurrence["points"]
            )
            support_anchors.extend(
                (
                    np.append(
                        np.asarray(
                            anchor["position_world_m"], dtype=np.float64
                        ),
                        1.0,
                    )
                    @ source_inverse
                )[:3].tolist()
                for anchor in occurrence["friction_anchors"]
            )
            for point in occurrence["points"]:
                local = (
                    np.append(
                        np.asarray(point["position_world_m"], dtype=np.float64),
                        1.0,
                    )
                    @ source_inverse
                )[:3]
                support_point_records.append(
                    {
                        "position_source_local_m": local.tolist(),
                        "source_normal_world": point["source_normal_world"],
                        "separation_m": float(point["separation_m"]),
                        "normal_impulse_n_s": float(
                            point["normal_impulse_n_s"]
                        ),
                    }
                )
            for anchor in occurrence["friction_anchors"]:
                local = (
                    np.append(
                        np.asarray(
                            anchor["position_world_m"], dtype=np.float64
                        ),
                        1.0,
                    )
                    @ source_inverse
                )[:3]
                support_anchor_records.append(
                    {
                        "position_source_local_m": local.tolist(),
                        "source_impulse_n_s": anchor[
                            "source_impulse_n_s"
                        ],
                    }
                )
            support_normal_impulse += float(
                occurrence["normal_impulse_n_s"]
            )
            support_friction_norm += float(
                occurrence["friction_anchor_norm_n_s"]
            )
        elif isinstance(other, str) and "leftfinger" in other:
            side_normal["left"] += float(occurrence["normal_impulse_n_s"])
        elif isinstance(other, str) and "rightfinger" in other:
            side_normal["right"] += float(occurrence["normal_impulse_n_s"])
    target_pair_ids = {
        str(row["pair_id"])
        for row in pair_table
        if row.get("target_pair") is True
    }
    if not target_pair_ids or "__source_support__" not in solver_caches:
        raise ProtocolBlocker(
            "prelift_solver_cache_partition_missing",
            f"targets={sorted(target_pair_ids)}:source_support={'__source_support__' in solver_caches}",
        )
    target_normal_cache = {}
    for pair_id in sorted(target_pair_ids):
        cache = solver_caches.get(pair_id)
        if not isinstance(cache, Mapping) or not isinstance(
            cache.get("normal_cache_float32_hex"), str
        ):
            raise ProtocolBlocker(
                "target_normal_cache_authority_missing", pair_id
            )
        target_normal_cache[pair_id] = cache["normal_cache_float32_hex"]
    non_target_caches = {
        key: value
        for key, value in solver_caches.items()
        if key not in target_pair_ids and key != "__source_support__"
    }
    non_target_cache_payload = _canonical_json_bytes(
        non_target_caches
    ).hex()
    source_support_cache_payload = _canonical_json_bytes(
        solver_caches["__source_support__"]
    ).hex()
    from scipy.spatial.transform import Rotation

    tool_matrix = np.asarray(
        authority_pre["tool_world_matrix"], dtype=np.float64
    )
    tool_xyzw = Rotation.from_matrix(tool_matrix[:3, :3].T).as_quat()
    return {
        "controller_event_sha256": _canonical_json_sha256(
            trajectory["comparison_summary"]["controller_events"]
        ),
        "action_sha256": lift["action_receipt"]["action_sha256"],
        "nonfinger_joint_positions_rad": joints[:7].tolist(),
        "nonfinger_joint_velocities_rad_s": joint_velocities[:7].tolist(),
        "finger_joint_positions_rad": joints[7:9].tolist(),
        "finger_joint_velocities_rad_s": joint_velocities[7:9].tolist(),
        "tool_position_m": authority_pre["tool_position_m"],
        "source_position_m": authority_pre["source_com_m"],
        "tool_orientation_wxyz": tool_xyzw[[3, 0, 1, 2]].tolist(),
        "source_orientation_wxyz": authority_pre[
            "source_orientation_wxyz"
        ],
        "tool_linear_velocity_m_s": authority_pre[
            "tool_linear_velocity_m_s"
        ],
        "source_linear_velocity_m_s": authority_pre[
            "source_linear_velocity_m_s"
        ],
        "tool_angular_velocity_rad_s": authority_pre[
            "tool_angular_velocity_rad_s"
        ],
        "source_angular_velocity_rad_s": authority_pre[
            "source_angular_velocity_rad_s"
        ],
        "left_target_points_source_local_m": side_points["left"],
        "right_target_points_source_local_m": side_points["right"],
        "left_normal_impulse_n_s": side_normal["left"],
        "right_normal_impulse_n_s": side_normal["right"],
        "support_lifecycle": contact.get("support_event"),
        "support_points_source_local_m": support_points,
        "support_anchors_source_local_m": support_anchors,
        "support_point_records": support_point_records,
        "support_anchor_records": support_anchor_records,
        "support_normal_impulse_n_s": support_normal_impulse,
        "support_friction_anchor_norm_n_s": support_friction_norm,
        "non_target_solver_cache_hex": non_target_cache_payload,
        "source_support_solver_cache_hex": source_support_cache_payload,
        "target_normal_cache": target_normal_cache,
        "predicate_margins": margins,
    }


def _run_runtime_child(args: argparse.Namespace) -> int:
    from isaacsim import SimulationApp

    app = None
    controller = None
    world = None
    audit = None
    report_written = False
    cleanup_written = False
    child_pid = os.getpid()
    run_id = secrets.token_hex(16)
    trace_records: list[dict[str, Any]] = []
    runtime_evidence: dict[str, Any] = {}
    report: dict[str, Any]
    exit_code = 1
    try:
        if Path.cwd().resolve() != args.out_dir.resolve():
            raise ProtocolBlocker(
                "treatment_working_directory_mismatch",
                f"cwd={Path.cwd().resolve()}:expected={args.out_dir.resolve()}",
            )
        if os.getppid() != args.parent_pid:
            raise RuntimeError(
                f"parent_pid_mismatch:actual={os.getppid()}:expected={args.parent_pid}"
            )
        frozen_bytes = args.frozen_config.read_bytes()
        if _sha256_bytes(frozen_bytes) != args.expected_config_sha256:
            raise RuntimeError("frozen_config_sha256_mismatch")
        if not frozen_bytes.endswith(b"\n") or b"\n" in frozen_bytes[:-1]:
            raise RuntimeError("frozen_config_line_contract_invalid")
        config = _decode_strict_json_line(frozen_bytes[:-1])
        if _canonical_json_bytes(config) != frozen_bytes:
            raise RuntimeError("frozen_config_not_canonical")
        if config.get("diagnostic", {}).get("treatments") != list(TREATMENTS):
            raise RuntimeError("frozen_config_protocol_mismatch")
        diagnostic = config["diagnostic"]

        app = SimulationApp(
            {"headless": bool(args.headless), "width": 64, "height": 64}
        )
        from isaacsim_compat import install_legacy_isaacsim_aliases

        install_legacy_isaacsim_aliases()
        import omni.kit.app
        import omni.usd
        from isaacsim.core.api import World
        from isaacsim.core.prims import SingleRigidPrim
        from isaacsim.core.utils.stage import add_reference_to_stage, get_stage_units
        from omegaconf import OmegaConf
        from omni.physx import get_physx_simulation_interface
        from omni.physx.scripts.physicsUtils import PhysicsSchemaTools
        from pxr import Usd, UsdUtils

        from factories.robot_factory import create_robot
        from factories.task_factory import create_task
        from factories.controller_factory import create_controller
        from utils.object_utils import ObjectUtils

        cfg = OmegaConf.create(config)
        stage = omni.usd.get_context().get_stage()
        world = World(
            stage_units_in_meters=1.0,
            physics_prim_path="/physicsScene",
            backend="numpy",
        )
        if not math.isclose(
            float(world.get_physics_dt()),
            float(diagnostic["physics_dt"]),
            rel_tol=0.0,
            abs_tol=float(diagnostic["physics_dt_tolerance_s"]),
        ):
            raise ProtocolBlocker(
                "physics_dt_mismatch",
                f"actual={world.get_physics_dt()}:expected={diagnostic['physics_dt']}",
            )
        simulation_interface = get_physx_simulation_interface()
        authority = _require_runtime_authority(simulation_interface)
        runtime_evidence["live_runtime_authority"] = authority
        stage_id = UsdUtils.StageCache.Get().Insert(stage).ToLongInt()
        orientation = _runtime_orientation_calibration(
            stage=stage,
            world=world,
            app=app,
            single_rigid_prim_type=SingleRigidPrim,
            simulation_interface=simulation_interface,
            resolve_path=PhysicsSchemaTools.intToSdfPath,
            stage_id=int(stage_id),
        )

        robot = create_robot(
            str(cfg.robot.type),
            position=np.asarray(cfg.robot.position, dtype=np.float64),
        )
        asset_path = (REPO_ROOT / str(cfg.usd_path)).resolve()
        add_reference_to_stage(usd_path=str(asset_path), prim_path="/World")
        object_utils = ObjectUtils.get_instance(stage)
        report_inventory_before = _runtime_report_api_inventory(stage)
        report_layer = None
        report_body_paths = (
            str(diagnostic["source_body_path"]),
            str(diagnostic["left_finger_body_path"]),
            str(diagnostic["right_finger_body_path"]),
            str(diagnostic["hand_body_path"]),
        )
        if args.treatment != "control":
            report_layer = _runtime_install_report_layer(
                stage,
                source_body_path=str(diagnostic["source_body_path"]),
                robot_report_body_paths=report_body_paths[1:],
            )
            report_layer["catalog_validation"] = (
                _validate_report_only_layer_catalog(
                    report_layer["authored_catalog"],
                    report_body_paths=report_body_paths,
                )
            )

        audit = _RuntimeCallAudit(
            source_paths=(
                str(diagnostic["source_reset_root_path"]),
                str(diagnostic["source_body_path"]),
            )
        )
        for method_name in (
            "set_object_position",
            "set_object_pose",
            "set_object_velocity",
            "set_world_pose",
            "set_world_poses",
            "set_velocities",
        ):
            audit.patch(
                object_utils,
                method_name,
                coverage_names=(
                    "object_utils_root_pose_velocity",
                    "object_utils_body_pose_velocity",
                ),
                count_name="root_body_pose_velocity_writers",
                source_scoped=True,
            )

        reset_counter = {"count": 0}
        original_world_reset = world.reset

        def counted_world_reset(*reset_args: Any, **reset_kwargs: Any) -> Any:
            reset_counter["count"] += 1
            return original_world_reset(*reset_args, **reset_kwargs)

        world.reset = counted_world_reset
        task = create_task(
            str(cfg.task_type),
            cfg=cfg,
            world=world,
            stage=stage,
            robot=robot,
        )
        seed = int(diagnostic["numpy_seed"])
        expected_rng = np.random.RandomState(seed)
        requested_source_position = [
            float(expected_rng.uniform(*cfg.task.obj_paths[0].position_range[axis]))
            for axis in ("x", "y", "z")
        ]
        np.random.seed(seed)
        task.reset()
        if reset_counter["count"] != 2:
            raise ProtocolBlocker(
                "bootstrap_reset_count_mismatch",
                f"actual={reset_counter['count']}:expected=2",
            )
        controller = create_controller(
            str(cfg.controller_type), cfg=cfg, robot=robot
        )
        if audit.reset_root_write_count != 1:
            raise ProtocolBlocker(
                "reset_root_writer_count_mismatch",
                f"actual={audit.reset_root_write_count}:expected=1",
            )
        readback_source_position = _runtime_row_matrix(
            stage, str(diagnostic["source_reset_root_path"])
        )[3, :3].tolist()
        requested_pose_sha256 = _canonical_json_sha256(
            requested_source_position
        )
        readback_pose_sha256 = _canonical_json_sha256(
            readback_source_position
        )

        source_body = SingleRigidPrim(
            prim_path=str(diagnostic["source_body_path"]),
            name=f"original_empty_contact_lift_source_{args.treatment}",
        )
        source_body.initialize()
        tool_body = SingleRigidPrim(
            prim_path=str(diagnostic["hand_body_path"]),
            name=f"original_empty_contact_lift_hand_{args.treatment}",
        )
        tool_body.initialize()
        live_mass_properties = _runtime_mass_properties(
            app, stage, str(diagnostic["source_body_path"])
        )
        for method_name in (
            "set_world_pose",
            "set_linear_velocity",
            "set_angular_velocity",
        ):
            audit.patch(
                source_body,
                method_name,
                coverage_names=("rigid_prim_singular_pose_velocity",),
                count_name="root_body_pose_velocity_writers",
                source_scoped=False,
            )
        audit.patch(
            source_body,
            "set_velocities",
            coverage_names=("rigid_prim_plural_pose_velocity",),
            count_name="root_body_pose_velocity_writers",
            source_scoped=False,
        )
        rigid_view = getattr(source_body, "_rigid_prim_view", None)
        for method_name in (
            "set_kinematic_targets",
            "apply_forces",
            "apply_forces_and_torques_at_position",
            "set_external_forces_and_torques",
        ):
            audit.patch(
                rigid_view,
                method_name,
                coverage_names=(
                    "physics_view_kinematic_targets",
                    "rigid_body_force_torque_impulse",
                    "physics_view_force_at_position",
                    "tensor_force_torque_impulse",
                ),
                count_name=(
                    "kinematic_targets"
                    if "kinematic" in method_name
                    else "forces_torques_impulses"
                ),
                source_scoped=False,
            )
        gripper_control = getattr(controller, "gripper_control", None)
        for method_name in (
            "add_object_to_gripper",
            "update_gripper",
            "release_object",
            "remove_object_from_gripper",
        ):
            audit.patch(
                gripper_control,
                method_name,
                coverage_names=("software_gripper_add_update_release",),
                count_name="software_gripper_attachments",
                source_scoped=False,
            )

        left_colliders = _runtime_enabled_colliders(
            stage, str(diagnostic["left_finger_body_path"])
        )
        right_colliders = _runtime_enabled_colliders(
            stage, str(diagnostic["right_finger_body_path"])
        )
        finger_colliders = [*left_colliders, *right_colliders]
        source_collider = str(diagnostic["source_collider_path"])
        support_collider = str(diagnostic["support_collider_path"])
        target_pairs = {
            _runtime_pair_key(source_collider, collider): side
            for side, colliders in (
                ("left", left_colliders),
                ("right", right_colliders),
            )
            for collider in colliders
        }
        geometry = {
            "gravity_world_m_s2": list(diagnostic["gravity_world_m_s2"]),
            "source": _runtime_bound(stage, source_collider),
            "finger_colliders": {
                path: _runtime_bound(stage, path) for path in finger_colliders
            },
            "target_pairs": [
                {
                    "side": side,
                    "finger_body": (
                        str(diagnostic["left_finger_body_path"])
                        if side == "left"
                        else str(diagnostic["right_finger_body_path"])
                    ),
                    "finger_collider": collider,
                    "source_collider": source_collider,
                }
                for side, colliders in (
                    ("left", left_colliders),
                    ("right", right_colliders),
                )
                for collider in colliders
            ],
        }
        source_contract = _runtime_source_contract(
            stage,
            source_body_path=str(diagnostic["source_body_path"]),
            source_collider_path=source_collider,
            support_path=support_collider,
            finger_body_paths=(
                str(diagnostic["left_finger_body_path"]),
                str(diagnostic["right_finger_body_path"]),
            ),
        )
        scene_identity = _runtime_scene_identity(
            stage,
            world,
            expected_scene_paths=diagnostic[
                "physics_scene_paths_in_traversal_order"
            ],
        )
        if not source_contract["valid"] or not scene_identity["valid"]:
            raise ProtocolBlocker(
                "runtime_scene_or_source_contract_mismatch",
                json.dumps(
                    {"source": source_contract, "scene": scene_identity},
                    sort_keys=True,
                ),
            )
        if not math.isclose(
            float(get_stage_units()), 1.0, rel_tol=0.0, abs_tol=0.0
        ):
            raise ProtocolBlocker(
                "stage_units_mismatch", str(get_stage_units())
            )
        dependency_closure = _runtime_dependency_closure(asset_path)
        if dependency_closure["unresolved"]:
            raise ProtocolBlocker(
                "local_dependency_closure_unresolved",
                json.dumps(dependency_closure["unresolved"]),
            )
        franka_identity = _runtime_default_franka_identity(stage)
        version_and_gpu_identity = _runtime_version_and_gpu_identity()
        report_inventory_after = _runtime_report_api_inventory(stage)
        baseline_bindings = [
            _runtime_material_binding(stage, path)
            for path in finger_colliders
        ]
        source_binding_before = _runtime_material_binding(stage, source_collider)
        support_binding_before = _runtime_material_binding(stage, support_collider)
        runtime_evidence.update(
            {
                "orientation_calibration": orientation,
                "stage_id": int(stage_id),
                "report_inventory_before": report_inventory_before,
                "report_inventory_after": report_inventory_after,
                "report_layer": (
                    None
                    if report_layer is None
                    else {
                        key: value
                        for key, value in report_layer.items()
                        if key != "layer"
                    }
                ),
                "scene_identity": scene_identity,
                "source_contract": source_contract,
                "source_live_mass_properties": live_mass_properties,
                "dependency_closure": dependency_closure,
                "default_franka_identity": franka_identity,
                "version_and_gpu_identity": version_and_gpu_identity,
                "geometry": geometry,
                "baseline_finger_material_bindings": baseline_bindings,
                "source_material_binding": source_binding_before,
                "support_material_binding": support_binding_before,
                "live_runtime_authority": authority,
                "requested_source_position_m": requested_source_position,
                "readback_source_position_m": readback_source_position,
                "reset_count": reset_counter["count"],
                "backend": "numpy",
                "gpu_override_requested": False,
            }
        )
        all_colliders = _runtime_all_enabled_colliders(stage)
        original_pair_table, original_caches = _runtime_live_pair_table(
            simulation_interface=simulation_interface,
            authority=authority,
            stage_id=int(stage_id),
            finger_colliders=finger_colliders,
            all_colliders=all_colliders,
            source_collider=source_collider,
        )
        source_support_live_material = _invoke_pair_authority(
            simulation_interface,
            authority["available_methods"]["live_solver_pair_materials"],
            stage_id=int(stage_id),
            collider0=source_collider,
            collider1=support_collider,
        )
        original_caches["__source_support__"] = _invoke_pair_authority(
            simulation_interface,
            authority["available_methods"]["contact_cache_and_warm_start"],
            stage_id=int(stage_id),
            collider0=source_collider,
            collider1=support_collider,
        )["value"]
        runtime_evidence["source_support_live_material"] = (
            source_support_live_material
        )
        effective_pair_table = original_pair_table
        solver_caches = original_caches
        ablation_delta = None
        if args.treatment == "zero_friction_ablation":
            if report_layer is None:
                raise ProtocolBlocker(
                    "ablation_session_layer_missing", args.treatment
                )
            ablation_delta = _runtime_define_zero_friction_material(
                stage,
                layer=report_layer["layer"],
                material_path=str(diagnostic["zero_friction_material_path"]),
                finger_colliders=finger_colliders,
                baseline_bindings=baseline_bindings,
                source_binding=source_binding_before,
            )
            ablation_catalog = _runtime_layer_catalog(
                report_layer["layer"]
            )
            ablation_delta["authored_catalog"] = ablation_catalog
            ablation_delta["catalog_validation"] = (
                _validate_ablation_layer_catalog(
                    ablation_catalog,
                    report_body_paths=report_body_paths,
                    finger_colliders=finger_colliders,
                    material_path=str(
                        diagnostic["zero_friction_material_path"]
                    ),
                    source_root_path=str(
                        diagnostic["source_reset_root_path"]
                    ),
                    support_path=support_collider,
                )
            )
            source_binding_after = _runtime_material_binding(
                stage, source_collider
            )
            support_binding_after = _runtime_material_binding(
                stage, support_collider
            )
            if (
                source_binding_after != source_binding_before
                or support_binding_after != support_binding_before
            ):
                raise ProtocolBlocker(
                    "source_or_support_material_graph_changed",
                    json.dumps(
                        {
                            "source_before": source_binding_before,
                            "source_after": source_binding_after,
                            "support_before": support_binding_before,
                            "support_after": support_binding_after,
                        },
                        sort_keys=True,
                    ),
                )
            effective_pair_table, solver_caches = _runtime_live_pair_table(
                simulation_interface=simulation_interface,
                authority=authority,
                stage_id=int(stage_id),
                finger_colliders=finger_colliders,
                all_colliders=all_colliders,
                source_collider=source_collider,
            )
            source_support_live_material_after = _invoke_pair_authority(
                simulation_interface,
                authority["available_methods"][
                    "live_solver_pair_materials"
                ],
                stage_id=int(stage_id),
                collider0=source_collider,
                collider1=support_collider,
            )
            solver_caches["__source_support__"] = _invoke_pair_authority(
                simulation_interface,
                authority["available_methods"][
                    "contact_cache_and_warm_start"
                ],
                stage_id=int(stage_id),
                collider0=source_collider,
                collider1=support_collider,
            )["value"]
            if source_support_live_material_after != source_support_live_material:
                raise ProtocolBlocker(
                    "source_support_live_material_changed",
                    json.dumps(
                        {
                            "before": source_support_live_material,
                            "after": source_support_live_material_after,
                        },
                        sort_keys=True,
                    ),
                )
            isolation = evaluate_ablation_pair_table(
                original_pair_table, effective_pair_table
            )
            if not isolation["protocol_valid"]:
                raise ProtocolBlocker(
                    "ablation_pair_isolation_invalid",
                    json.dumps(isolation["protocol_failures"]),
                    evidence=isolation,
                )
        runtime_evidence["ablation_delta"] = ablation_delta

        audit.seal_stage_baseline(stage)
        audit.open_epoch()
        reporter = None
        if args.treatment != "control":
            reporter = _CompleteRuntimeReporter(
                get_full_contact_report=simulation_interface.get_full_contact_report,
                resolve_path=PhysicsSchemaTools.intToSdfPath,
                expected_stage_id=int(stage_id),
                provisional_background_pairs=((source_collider, support_collider),),
            )
        trajectory = _runtime_execute_trajectory(
            world=world,
            task=task,
            controller=controller,
            robot=robot,
            source_body=source_body,
            tool_body=tool_body,
            source_com_local_m=live_mass_properties[
                "center_of_mass_local_m"
            ],
            stage=stage,
            reporter=reporter,
            geometry=geometry if reporter is not None else None,
            source_collider=source_collider,
            support_collider=support_collider,
            target_pairs=target_pairs,
            orientation=orientation if reporter is not None else None,
            audit=audit,
            maximum_steps=int(diagnostic["maximum_production_steps"]),
            retention_steps=int(diagnostic["retention_steps"]),
            requested_pose_sha256=requested_pose_sha256,
            readback_pose_sha256=readback_pose_sha256,
            config_sha256=args.expected_config_sha256,
        )
        audit_result = evaluate_prohibited_mechanism_audit(audit.report())
        if not audit_result["protocol_valid"]:
            raise ProtocolBlocker(
                "prohibited_mechanism_audit_invalid",
                json.dumps(audit_result["protocol_failures"]),
                evidence=audit.report(),
            )
        prelift = (
            _runtime_prelift_parity_record(
                trajectory,
                solver_caches=solver_caches,
                pair_table=effective_pair_table,
            )
            if args.treatment != "control"
            else {}
        )
        if args.treatment == "zero_friction_ablation":
            evaluation = evaluate_zero_friction_trace(
                trajectory["transitions"],
                retention_steps=int(diagnostic["retention_steps"]),
                rise_threshold_m=float(diagnostic["rise_threshold_m"]),
                maximum_rise_m=float(diagnostic["maximum_ablation_rise_m"]),
                maximum_friction_anchor_norm_n_s=float(
                    diagnostic["maximum_zero_friction_anchor_norm_n_s"]
                ),
            )
            measurement_decision = (
                "ORIGINAL_EMPTY_BEAKER_FRICTION_CAUSAL_PASS"
                if evaluation["causal_negative_passed"]
                else "ZERO_FRICTION_CAUSALITY_FAIL"
            )
        elif args.treatment == "instrumented_original":
            evaluation = evaluate_original_lift_trace(
                trajectory["transitions"],
                physics_dt=float(diagnostic["physics_dt"]),
                retention_steps=int(diagnostic["retention_steps"]),
                rise_threshold_m=float(diagnostic["rise_threshold_m"]),
            )
            measurement_decision = (
                "ORIGINAL_EMPTY_BEAKER_FRICTION_CAUSAL_PASS"
                if evaluation["contact_lift_passed"]
                and evaluation["retention_passed"]
                else "ORIGINAL_EMPTY_BEAKER_CONTACT_LIFT_FAIL"
            )
        else:
            evaluation = {
                "terminal_outcome": trajectory["terminal_outcome"],
                "retention_steps": len(
                    trajectory["comparison_summary"]["continuation"]
                ),
            }
            measurement_decision = (
                "ORIGINAL_EMPTY_BEAKER_FRICTION_CAUSAL_PASS"
                if trajectory["terminal_outcome"] == "POURING"
                else "ORIGINAL_EMPTY_BEAKER_CONTACT_LIFT_FAIL"
            )
        for payload in trajectory["transitions"]:
            trace_records.append(
                make_trace_record(
                    trace_records,
                    treatment=args.treatment,
                    run_nonce=args.run_nonce,
                    parent_pid=args.parent_pid,
                    child_pid=child_pid,
                    run_id=run_id,
                    kind="transition",
                    payload=payload,
                )
            )
        report = {
            "schema_version": 1,
            "manifest_type": CHILD_MANIFEST_TYPE,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "lifecycle_status": "measurement_complete_pending_application_close",
            "shutdown_status": "pending",
            "treatment": args.treatment,
            "run_nonce": args.run_nonce,
            "parent_pid": args.parent_pid,
            "child_pid": child_pid,
            "run_id": run_id,
            "measurement_decision": measurement_decision,
            "protocol_blockers": [],
            "physical_failure": measurement_decision
            in {
                "ORIGINAL_EMPTY_BEAKER_CONTACT_LIFT_FAIL",
                "ZERO_FRICTION_CAUSALITY_FAIL",
            },
            "causal_pass": False,
            "runtime_evidence": runtime_evidence,
            "treatment_evaluation": evaluation,
            "comparison_summary": trajectory["comparison_summary"],
            "effective_pair_table": effective_pair_table,
            "prelift_parity": prelift,
            "prohibited_mechanism_audit": audit.report(),
        }
        exit_code = 0
    except ProtocolBlocker as exc:
        if exc.evidence is not None:
            runtime_evidence["protocol_blocker_evidence"] = exc.evidence
        if not trace_records:
            trace_records.append(
                make_trace_record(
                    trace_records,
                    treatment=args.treatment,
                    run_nonce=args.run_nonce,
                    parent_pid=args.parent_pid,
                    child_pid=child_pid,
                    run_id=run_id,
                    kind="bootstrap",
                    payload={"runtime_evidence": runtime_evidence},
                )
            )
        trace_records.append(
            make_trace_record(
                trace_records,
                treatment=args.treatment,
                run_nonce=args.run_nonce,
                parent_pid=args.parent_pid,
                child_pid=child_pid,
                run_id=run_id,
                kind="protocol_blocker",
                payload={
                    "code": exc.code,
                    "detail": exc.detail,
                    "evidence": exc.evidence,
                },
            )
        )
        report = protocol_no_go_report(
            treatment=args.treatment,
            run_nonce=args.run_nonce,
            parent_pid=args.parent_pid,
            child_pid=child_pid,
            run_id=run_id,
            blocker_code=exc.code,
            blocker_detail=exc.detail,
        )
        report["runtime_evidence"] = runtime_evidence
        exit_code = 0
    except BaseException as exc:
        if not trace_records:
            trace_records.append(
                make_trace_record(
                    trace_records,
                    treatment=args.treatment,
                    run_nonce=args.run_nonce,
                    parent_pid=args.parent_pid,
                    child_pid=child_pid,
                    run_id=run_id,
                    kind="bootstrap",
                    payload={"runtime_evidence": runtime_evidence},
                )
            )
        report = _runtime_error_child_report(
            exc,
            treatment=args.treatment,
            run_nonce=args.run_nonce,
            parent_pid=args.parent_pid,
            child_pid=child_pid,
            run_id=run_id,
            phase="runtime_measurement",
        )
        report["runtime_evidence"] = runtime_evidence
        exit_code = 1

    try:
        trace_records.append(
            make_trace_record(
                trace_records,
                treatment=args.treatment,
                run_nonce=args.run_nonce,
                parent_pid=args.parent_pid,
                child_pid=child_pid,
                run_id=run_id,
                kind="terminal",
                payload={
                    "measurement_decision": report["measurement_decision"],
                    "protocol_blocker_count": len(
                        report.get("protocol_blockers", [])
                    ),
                },
            )
        )
        trace_path = args.out_dir / TRACE_BASENAME
        atomic_create_jsonl(trace_path, trace_records)
        report["trace_chain_sha256"] = trace_records[-1]["record_sha256"]
        report["artifacts"] = {
            "frozen_config": _artifact_record(
                args.frozen_config, relative_to=args.out_dir
            ),
            "trace": _artifact_record(trace_path, relative_to=args.out_dir),
        }
        provisional_path = args.out_dir / PROVISIONAL_REPORT_BASENAME
        world_counter_before_cleanup = (
            _runtime_world_counter(world) if world is not None else None
        )
        atomic_create_json(provisional_path, report)
        report_written = True
        collector_closed = False
        if controller is not None:
            controller.close()
            collector_closed = True
        world_counter_after_controller_close = (
            _runtime_world_counter(world) if world is not None else None
        )
        if world_counter_after_controller_close != world_counter_before_cleanup:
            raise RuntimeError("controller_cleanup_advanced_world_counter")
        if audit is not None:
            audit.close()
        cleanup = {
            "schema_version": 1,
            "manifest_type": "original_empty_beaker_contact_lift_cleanup_v1",
            "treatment": args.treatment,
            "run_nonce": args.run_nonce,
            "parent_pid": args.parent_pid,
            "child_pid": child_pid,
            "run_id": run_id,
            "trace_chain_sha256": trace_records[-1]["record_sha256"],
            "controller_closed": controller is None or collector_closed,
            "collector_closed": controller is None or collector_closed,
            "world_counter_before_cleanup": world_counter_before_cleanup,
            "world_counter_after_controller_close": (
                world_counter_after_controller_close
            ),
        }
        atomic_create_json(args.out_dir / CLEANUP_BASENAME, cleanup)
        cleanup_written = True
    except BaseException:
        exit_code = 1
    finally:
        if app is not None:
            try:
                app.close()
            except BaseException:
                exit_code = 1
    if not report_written or not cleanup_written:
        return 1
    return exit_code


def _validate_cleanup_receipt(
    cleanup: Mapping[str, Any],
    *,
    treatment: str,
    run_nonce: str,
    parent_pid: int,
    child_pid: int,
    run_id: str,
    trace_chain_sha256: str,
) -> dict[str, Any]:
    valid = bool(
        isinstance(cleanup, Mapping)
        and cleanup.get("schema_version") == 1
        and cleanup.get("manifest_type")
        == "original_empty_beaker_contact_lift_cleanup_v1"
        and cleanup.get("treatment") == treatment
        and cleanup.get("run_nonce") == run_nonce
        and cleanup.get("parent_pid") == parent_pid
        and cleanup.get("child_pid") == child_pid
        and cleanup.get("run_id") == run_id
        and cleanup.get("trace_chain_sha256") == trace_chain_sha256
        and cleanup.get("controller_closed") is True
        and cleanup.get("collector_closed") is True
        and cleanup.get("world_counter_before_cleanup")
        == cleanup.get("world_counter_after_controller_close")
    )
    if not valid:
        raise ValueError("probe_cleanup_receipt_invalid")
    return {**dict(cleanup), "valid": True}


def _synthetic_parent_runtime_error(
    exc: BaseException,
    *,
    treatment: str,
    run_nonce: str,
    parent_pid: int,
    child_pid: int,
    phase: str,
) -> dict[str, Any]:
    return _runtime_error_child_report(
        exc,
        treatment=treatment,
        run_nonce=run_nonce,
        parent_pid=parent_pid,
        child_pid=child_pid,
        run_id=f"parent-error-{treatment}",
        phase=phase,
    )


def _run_parent(args: argparse.Namespace) -> int:
    parent_pid = os.getpid()
    try:
        args.out_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
        os.chmod(args.out_dir, 0o700)
    except FileExistsError:
        print(
            f"original empty contact-lift probe refused existing output: {args.out_dir}",
            file=sys.stderr,
            flush=True,
        )
        return 2
    child_results: dict[str, dict[str, Any]] = {}
    trace_records: dict[str, list[dict[str, Any]]] = {}
    parent_artifacts: dict[str, Any] = {}
    frozen: dict[str, Any] | None = None
    parent_identity: dict[str, Any] | None = None
    parent_error: str | None = None
    try:
        frozen = freeze_diagnostic_config(
            args.config, production_config_path=PRODUCTION_CONFIG
        )
        baseline_identity = _implementation_identity(frozen["config"])
        parent_identity = baseline_identity
        run_nonce = secrets.token_hex(16)
        launch_allowed = True
        for treatment in TREATMENTS:
            treatment_dir = args.out_dir / treatment
            frozen_path = write_frozen_config(
                frozen["canonical_bytes"], treatment_dir
            )
            command = build_child_command(
                treatment=treatment,
                frozen_config_path=frozen_path,
                treatment_dir=treatment_dir,
                run_nonce=run_nonce,
                parent_pid=parent_pid,
                expected_config_sha256=frozen["sha256"],
            )
            stdout_path = treatment_dir / "child.stdout.log"
            stderr_path = treatment_dir / "child.stderr.log"
            timed_out = False
            termination = None
            child_returncode = 127
            child_pid = 1
            process = None
            cleanup_quiescent = False
            provisional: Mapping[str, Any]
            phase = "preflight_identity"
            if not launch_allowed:
                exc = RuntimeError(
                    "previous_treatment_cleanup_not_quiescent"
                )
                provisional = _synthetic_parent_runtime_error(
                    exc,
                    treatment=treatment,
                    run_nonce=run_nonce,
                    parent_pid=parent_pid,
                    child_pid=child_pid,
                    phase=phase,
                )
                atomic_create_json(stdout_path.with_suffix(".placeholder.json"), {"not_launched": True})
                child_results[treatment] = finalize_child_result(
                    provisional,
                    expected_treatment=treatment,
                    expected_run_nonce=run_nonce,
                    expected_parent_pid=parent_pid,
                    expected_child_pid=child_pid,
                    child_command=command,
                    child_returncode=127,
                    timed_out=False,
                    termination=None,
                    cleanup_quiescent=False,
                )
                continue
            with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
                try:
                    if _implementation_identity(frozen["config"]) != baseline_identity:
                        raise ValueError("identity_changed_before_child")
                    phase = "child_launch"
                    process = subprocess.Popen(
                        command,
                        cwd=str(treatment_dir),
                        env={
                            **os.environ,
                            "PYTHONUNBUFFERED": "1",
                            "PYTHONPATH": os.pathsep.join(
                                filter(
                                    None,
                                    (
                                        str(REPO_ROOT),
                                        os.environ.get("PYTHONPATH", ""),
                                    ),
                                )
                            ),
                        },
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
                        termination = terminate_process_group(process)
                        child_returncode = (
                            int(process.returncode)
                            if process.returncode is not None
                            else -signal.SIGKILL
                        )
                    phase = "identity_postflight"
                    if _implementation_identity(frozen["config"]) != baseline_identity:
                        raise ValueError("identity_changed_during_child")
                    phase = "provisional_artifacts"
                    provisional = load_strict_json_object(
                        treatment_dir / PROVISIONAL_REPORT_BASENAME
                    )
                    validated_artifacts = _validate_child_artifacts(
                        provisional,
                        treatment_dir=treatment_dir,
                        expected_config_sha256=frozen["sha256"],
                        expected_parent_pid=parent_pid,
                        expected_child_pid=child_pid,
                        expected_nonce=run_nonce,
                    )
                    trace_records[treatment] = validated_artifacts["records"]
                    cleanup = load_strict_json_object(
                        treatment_dir / CLEANUP_BASENAME
                    )
                    cleanup_receipt = _validate_cleanup_receipt(
                        cleanup,
                        treatment=treatment,
                        run_nonce=run_nonce,
                        parent_pid=parent_pid,
                        child_pid=child_pid,
                        run_id=str(provisional["run_id"]),
                        trace_chain_sha256=str(
                            provisional["trace_chain_sha256"]
                        ),
                    )
                    phase = "process_quiescence"
                    deadline = time.monotonic() + 2.0
                    while True:
                        try:
                            validate_process_quiescence(
                                process,
                                collector_closed=cleanup_receipt[
                                    "collector_closed"
                                ],
                            )
                            cleanup_quiescent = True
                            break
                        except RuntimeError:
                            if time.monotonic() >= deadline:
                                raise
                            time.sleep(0.05)
                except BaseException as exc:
                    if process is not None and process.poll() is None:
                        try:
                            termination = terminate_process_group(process)
                        except BaseException as cleanup_exc:
                            termination = (
                                f"CLEANUP_ERROR:{type(cleanup_exc).__name__}:"
                                f"{cleanup_exc}"
                            )
                    if process is not None and process.returncode is not None:
                        child_returncode = int(process.returncode)
                    provisional = _synthetic_parent_runtime_error(
                        exc,
                        treatment=treatment,
                        run_nonce=run_nonce,
                        parent_pid=parent_pid,
                        child_pid=child_pid,
                        phase=phase,
                    )
                    cleanup_quiescent = False
            result = finalize_child_result(
                provisional,
                expected_treatment=treatment,
                expected_run_nonce=run_nonce,
                expected_parent_pid=parent_pid,
                expected_child_pid=child_pid,
                child_command=command,
                child_returncode=child_returncode,
                timed_out=timed_out,
                termination=termination,
                cleanup_quiescent=cleanup_quiescent,
            )
            treatment_tree = _validate_treatment_tree(treatment_dir)
            result["parent_identity"] = baseline_identity
            result["treatment_tree"] = treatment_tree
            result["parent_artifacts"] = {
                "child_stdout": _artifact_record(
                    stdout_path, relative_to=treatment_dir
                ),
                "child_stderr": _artifact_record(
                    stderr_path, relative_to=treatment_dir
                ),
            }
            child_results[treatment] = result
            parent_artifacts[treatment] = {
                "child_stdout": _artifact_record(
                    stdout_path, relative_to=args.out_dir
                ),
                "child_stderr": _artifact_record(
                    stderr_path, relative_to=args.out_dir
                ),
                "frozen_config": _artifact_record(
                    frozen_path, relative_to=args.out_dir
                ),
            }
            if not cleanup_quiescent:
                launch_allowed = False
        recalculated = recompute_final_evidence(
            child_results,
            trace_records,
            config=frozen["config"],
        )
    except BaseException as exc:
        parent_error = f"{type(exc).__name__}:{exc}"
        components = {
            "runtime_error": True,
            "protocol_no_go": False,
            "contact_report_perturbation": False,
            "original_contact_lift_passed": False,
            "retention_continuation_passed": False,
            "zero_friction_causality_passed": False,
        }
        recalculated = {
            "components": components,
            "decision": select_decision(components),
            "evaluations": {},
        }
    report = {
        "schema_version": 1,
        "manifest_type": MANIFEST_TYPE,
        "finalized_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision": recalculated["decision"],
        "components": recalculated["components"],
        "parent_recalculation": recalculated["evaluations"],
        "parent_pid": parent_pid,
        "parent_error": parent_error,
        "parent_identity": parent_identity,
        "frozen_config": (
            None
            if frozen is None
            else {
                key: value
                for key, value in frozen.items()
                if key not in {"config", "canonical_bytes"}
            }
        ),
        "child_results": child_results,
        "artifacts": parent_artifacts,
        "runtime_launched": bool(child_results),
        "gpu_launched": False,
    }
    atomic_create_json(args.out_dir / FINAL_REPORT_BASENAME, report)
    print(
        f"original empty contact-lift probe decision={report['decision']} "
        f"out={args.out_dir / FINAL_REPORT_BASENAME}",
        flush=True,
    )
    return 0 if report["decision"] != "PROBE_RUNTIME_ERROR" else 2


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=240.0)
    parser.add_argument("--runtime-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--treatment", choices=TREATMENTS, help=argparse.SUPPRESS)
    parser.add_argument("--frozen-config", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--run-nonce", default="", help=argparse.SUPPRESS)
    parser.add_argument("--parent-pid", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument(
        "--expected-config-sha256", default="", help=argparse.SUPPRESS
    )
    args = parser.parse_args(argv)
    args.config = args.config.resolve()
    args.out_dir = args.out_dir.resolve()
    if (
        not math.isfinite(args.timeout_seconds)
        or args.timeout_seconds <= 0.0
    ):
        parser.error("timeout must be finite and positive")
    if args.runtime_child:
        if (
            args.treatment not in TREATMENTS
            or args.frozen_config is None
            or not args.run_nonce
            or args.parent_pid <= 0
            or not _is_sha256(args.expected_config_sha256)
            or not args.out_dir.is_dir()
        ):
            parser.error("runtime child identity arguments are incomplete")
        args.frozen_config = args.frozen_config.resolve()
        if not args.frozen_config.is_file():
            parser.error("runtime child frozen config is missing")
    else:
        if not args.config.is_file():
            parser.error(f"config not found: {args.config}")
        if any(
            (
                args.treatment is not None,
                args.frozen_config is not None,
                bool(args.run_nonce),
                args.parent_pid != 0,
                bool(args.expected_config_sha256),
            )
        ):
            parser.error("runtime child arguments are parent-managed")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return _run_runtime_child(args) if args.runtime_child else _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
