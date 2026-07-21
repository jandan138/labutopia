"""Fail-closed, Isaac-free contracts for the real PBD grasp v2 route.

This module deliberately does not import the legacy probe runners.  It defines
the evidence gates that a later Isaac child must satisfy before it can progress
from geometry, to passive baseline, to a close-only bilateral contact attempt.
Its hashes make receipts tamper-evident and mutually consistent; a parent-owned
runtime and protected issuer remain required to make a positive artifact trusted.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import secrets
import stat
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from utils.controlled_contact import (
    build_arm_target_token,
    build_finger_target_token,
    canonical_json_sha256,
)


_SHA256_CHARACTERS = frozenset("0123456789abcdef")
_G2_PHASES = frozenset(
    {
        "PREGRASP",
        "ALIGN",
        "INSERT",
        "SETTLE",
        "PRECONTACT_SETTLE",
        "CLOSE",
        "CONTACT_SETTLE",
    }
)
_G2_PRECONTACT_PHASES = frozenset({"INSERT", "SETTLE", "PRECONTACT_SETTLE"})
_G2_CLOSE_PHASES = frozenset({"CLOSE", "CONTACT_SETTLE"})
_G2_ACTION_KINDS = {
    "PREGRASP": frozenset({"GRIPPER_OPEN", "ARM_PREGRASP"}),
    "ALIGN": frozenset({"ARM_ALIGN"}),
    "INSERT": frozenset({"ARM_INSERT"}),
    "SETTLE": frozenset({"ARM_SETTLE"}),
    "PRECONTACT_SETTLE": frozenset({"ARM_PRECONTACT_SETTLE"}),
    "CLOSE": frozenset({"GRIPPER_CLOSE"}),
    "CONTACT_SETTLE": frozenset({"GRIPPER_CONTACT_SETTLE"}),
}
_CONTACT_CLASSES = frozenset(
    {
        "BACKGROUND",
        "INTENDED_PRECONTACT",
        "INTENDED_CLOSE_CONTACT",
        "PROHIBITED_CONTACT",
        "UNKNOWN_CONTACT",
    }
)
_STAGE_PREDECESSORS = {
    "G0": (),
    "G1-D": ("G0",),
    "G1-F": ("G0",),
    "G1-COMPARE": ("G1-D", "G1-F"),
    "G2-D": ("G0", "G1-COMPARE"),
    "G2-F": ("G0", "G1-COMPARE", "G2-D"),
}
_STAGE_GO_DECISIONS = {
    "G0": "G0_GO",
    "G1-D": "G1_D_GO",
    "G1-F": "G1_F_GO",
    "G1-COMPARE": "G1_GO",
    "G2-D": "G2_D_GO",
    "G2-F": "G2_F_GO",
}
_STAGE_ALLOWED_DECISIONS = {
    stage: frozenset((decision, decision.removesuffix("_GO") + "_NO_GO"))
    for stage, decision in _STAGE_GO_DECISIONS.items()
}


def _error(stage: str, reason: str) -> ValueError:
    return ValueError(f"real_pbd_{stage}_{reason}")


def _sha256(value: Any, *, stage: str, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _SHA256_CHARACTERS for character in value)
    ):
        raise _error(stage, f"{field}_invalid")
    return value


def _nonnegative_index(value: Any, *, stage: str, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise _error(stage, f"{field}_invalid")
    result = int(value)
    if result < 0:
        raise _error(stage, f"{field}_invalid")
    return result


def _finite_number(
    value: Any,
    *,
    stage: str,
    field: str,
    nonnegative: bool = False,
    positive: bool = False,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float, np.number))
        or not math.isfinite(float(value))
    ):
        raise _error(stage, f"{field}_invalid")
    result = float(value)
    if positive and result <= 0.0:
        raise _error(stage, f"{field}_invalid")
    if nonnegative and result < 0.0:
        raise _error(stage, f"{field}_invalid")
    return result


def _finite_vector(
    value: Any,
    *,
    shape: tuple[int, ...],
    stage: str,
    field: str,
    unit: bool = False,
) -> np.ndarray:
    try:
        result = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise _error(stage, f"{field}_invalid") from exc
    if result.shape != shape or not np.isfinite(result).all():
        raise _error(stage, f"{field}_invalid")
    if unit:
        norm = float(np.linalg.norm(result))
        if norm <= 1.0e-12:
            raise _error(stage, f"{field}_invalid")
        result = result / norm
    return result


def _path(value: Any, *, stage: str, field: str) -> str:
    if not isinstance(value, str) or not value.startswith("/"):
        raise _error(stage, f"{field}_invalid")
    return value


def _path_list(
    value: Any,
    *,
    stage: str,
    field: str,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _error(stage, f"{field}_invalid")
    result = [_path(item, stage=stage, field=field) for item in value]
    if (not allow_empty and not result) or len(result) != len(set(result)):
        raise _error(stage, f"{field}_invalid")
    return result


def _pair(value: Any, *, stage: str, field: str) -> tuple[str, str]:
    paths = _path_list(value, stage=stage, field=field)
    if len(paths) != 2:
        raise _error(stage, f"{field}_invalid")
    return tuple(sorted(paths))


def _matrix(value: Any, *, stage: str, field: str) -> np.ndarray:
    matrix = _finite_vector(value, shape=(4, 4), stage=stage, field=field)
    if not math.isclose(float(matrix[3, 3]), 1.0, rel_tol=0.0, abs_tol=1.0e-12):
        raise _error(stage, f"{field}_invalid")
    return matrix


def _matrix_sha256(matrix: np.ndarray) -> str:
    raw = np.ascontiguousarray(matrix, dtype=np.dtype("<f8")).tobytes(order="C")
    return hashlib.sha256(raw).hexdigest()


def _hash_checked_mapping(
    value: Any,
    *,
    stage: str,
    authority: str,
    hash_field: str = "evidence_sha256",
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _error(stage, "evidence_mapping_required")
    payload = copy.deepcopy(dict(value))
    digest = payload.pop(hash_field, None)
    _sha256(digest, stage=stage, field=hash_field)
    if payload.get("authority") != authority:
        raise _error(stage, "evidence_authority_invalid")
    if canonical_json_sha256(payload) != digest:
        raise _error(stage, "evidence_hash_mismatch")
    return {**payload, hash_field: digest}


def _validate_g0_fixture(value: Any) -> tuple[dict[str, Any], set[str]]:
    stage = "g0"
    if not isinstance(value, Mapping):
        raise _error(stage, "fixture_mapping_required")
    fixture = copy.deepcopy(dict(value))
    for field in (
        "usd_dependency_closure_sha256",
        "composed_collision_inventory_sha256",
    ):
        _sha256(fixture.get(field), stage=stage, field=field)
    _path(fixture.get("source_actor_path"), stage=stage, field="source_actor_path")
    _path(fixture.get("particle_path"), stage=stage, field="particle_path")
    external = _path_list(
        fixture.get("source_external_shell_paths"),
        stage=stage,
        field="source_external_shell_paths",
    )
    wrappers = _path_list(
        fixture.get("source_internal_wrapper_paths"),
        stage=stage,
        field="source_internal_wrapper_paths",
    )
    support = _path_list(
        fixture.get("support_collider_paths"),
        stage=stage,
        field="support_collider_paths",
    )
    hand = _path_list(
        fixture.get("hand_collider_paths"),
        stage=stage,
        field="hand_collider_paths",
    )
    finger_paths = fixture.get("finger_pad_collider_paths")
    if not isinstance(finger_paths, Mapping) or set(finger_paths) != {"left", "right"}:
        raise _error(stage, "finger_pad_collider_paths_invalid")
    left = _path_list(
        finger_paths["left"], stage=stage, field="left_finger_pad_collider_paths"
    )
    right = _path_list(
        finger_paths["right"], stage=stage, field="right_finger_pad_collider_paths"
    )
    all_paths = [*external, *wrappers, *support, *hand, *left, *right]
    if len(all_paths) != len(set(all_paths)):
        raise _error(stage, "fixture_collider_paths_duplicate")
    return fixture, set(all_paths)


def _validate_g0_offsets(value: Any, *, required_paths: set[str]) -> dict[str, Any]:
    stage = "g0"
    if not isinstance(value, Mapping) or not required_paths <= set(value):
        raise _error(stage, "effective_offsets_invalid")
    result: dict[str, Any] = {}
    for path in required_paths:
        record = value.get(path)
        if not isinstance(record, Mapping):
            raise _error(stage, "effective_offsets_invalid")
        authority = record.get("authority")
        if authority not in {
            "runtime_effective_physx_v1",
            "runtime_effective_physx_cooked_v1",
        }:
            raise _error(stage, "effective_offsets_invalid")
        result[path] = {
            "contact_offset_m": _finite_number(
                record.get("contact_offset_m"),
                stage=stage,
                field="contact_offset",
                nonnegative=True,
            ),
            "rest_offset_m": _finite_number(
                record.get("rest_offset_m"), stage=stage, field="rest_offset"
            ),
            "authority": authority,
        }
    return result


def _validate_g0_load_input(value: Any) -> dict[str, Any]:
    stage = "g0"
    if not isinstance(value, Mapping):
        raise _error(stage, "load_input_authority_invalid")
    authority = value.get("particle_density_or_mass_authority")
    if authority != "runtime_readback_required_v1":
        raise _error(stage, "load_input_authority_invalid")
    particle_count = _nonnegative_index(
        value.get("particle_count"), stage=stage, field="particle_count"
    )
    if particle_count == 0:
        raise _error(stage, "particle_count_invalid")
    dry_mass = _finite_number(
        value.get("source_dry_mass_kg"),
        stage=stage,
        field="source_dry_mass",
        positive=True,
    )
    gravity = _finite_vector(
        value.get("gravity_world_m_s2"),
        shape=(3,),
        stage=stage,
        field="gravity",
    )
    if float(np.linalg.norm(gravity)) <= 1.0e-12:
        raise _error(stage, "gravity_invalid")
    _sha256(value.get("solver_settings_sha256"), stage=stage, field="solver_settings")
    if type(value.get("runtime_filled_load_verified")) is not bool:
        raise _error(stage, "load_input_authority_invalid")
    return {
        "particle_count": particle_count,
        "source_dry_mass_kg": dry_mass,
        "gravity_world_m_s2": gravity.tolist(),
        "runtime_filled_load_verified": value["runtime_filled_load_verified"],
    }


def _validate_g0_candidates(
    value: Any, *, required_paths: set[str]
) -> tuple[list[dict[str, Any]], str, dict[str, bool]]:
    stage = "g0"
    if not isinstance(value, Mapping):
        raise _error(stage, "candidate_set_invalid")
    if value.get("authority") != "g0_predeclared_finite_candidate_set_v1":
        raise _error(stage, "candidate_set_invalid")
    selected = value.get("selected_candidate_id")
    if not isinstance(selected, str) or not selected:
        raise _error(stage, "candidate_set_invalid")
    raw_candidates = value.get("candidates")
    if not isinstance(raw_candidates, Sequence) or isinstance(
        raw_candidates, (str, bytes, bytearray)
    ) or not raw_candidates:
        raise _error(stage, "candidate_set_invalid")

    normalized = []
    identifiers = set()
    all_strictly_positive = True
    all_precontact_positive = True
    all_paths_covered = True
    for raw in raw_candidates:
        if not isinstance(raw, Mapping):
            raise _error(stage, "candidate_invalid")
        candidate = copy.deepcopy(dict(raw))
        identifier = candidate.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise _error(stage, "candidate_invalid")
        identifiers.add(identifier)
        _sha256(candidate.get("target_spec_sha256"), stage=stage, field="target_spec")
        close_endpoint = _finite_number(
            candidate.get("close_endpoint_m"),
            stage=stage,
            field="close_endpoint",
            positive=True,
        )
        if close_endpoint > 0.04:
            raise _error(stage, "close_endpoint_invalid")
        envelope = candidate.get("tracking_envelope")
        if not isinstance(envelope, Mapping):
            raise _error(stage, "tracking_envelope_invalid")
        _finite_number(
            envelope.get("maximum_position_error_m"),
            stage=stage,
            field="tracking_position_error",
            nonnegative=True,
        )
        _finite_number(
            envelope.get("maximum_orientation_error_degrees"),
            stage=stage,
            field="tracking_orientation_error",
            nonnegative=True,
        )
        precontact = candidate.get("precontact_pad_shell_clearance_m")
        if not isinstance(precontact, Mapping) or set(precontact) != {"left", "right"}:
            raise _error(stage, "precontact_pad_shell_clearance_invalid")
        precontact_values = {
            side: _finite_number(
                precontact[side],
                stage=stage,
                field=f"precontact_{side}_clearance",
                positive=True,
            )
            for side in ("left", "right")
        }
        all_precontact_positive = all(
            (*precontact_values.values(), all_precontact_positive)
        )
        sweeps = candidate.get("prohibited_sweeps")
        if not isinstance(sweeps, Sequence) or isinstance(
            sweeps, (str, bytes, bytearray)
        ) or not sweeps:
            raise _error(stage, "prohibited_sweeps_invalid")
        covered_paths = set()
        normalized_sweeps = []
        for raw_sweep in sweeps:
            if not isinstance(raw_sweep, Mapping):
                raise _error(stage, "prohibited_sweep_invalid")
            pair = _pair(
                raw_sweep.get("collider_paths"), stage=stage, field="sweep_collider_paths"
            )
            if not set(pair) <= required_paths:
                raise _error(stage, "prohibited_sweep_invalid")
            clearance = _finite_number(
                raw_sweep.get("minimum_signed_clearance_m"),
                stage=stage,
                field="minimum_signed_clearance",
            )
            samples = _nonnegative_index(
                raw_sweep.get("sample_count"), stage=stage, field="sweep_sample_count"
            )
            if samples == 0:
                raise _error(stage, "sweep_sample_count_invalid")
            covered_paths.update(pair)
            all_strictly_positive = all_strictly_positive and clearance > 0.0
            normalized_sweeps.append(
                {
                    "collider_paths": list(pair),
                    "minimum_signed_clearance_m": clearance,
                    "sample_count": samples,
                }
            )
        all_paths_covered = all_paths_covered and required_paths <= covered_paths
        normalized.append(
            {
                "id": identifier,
                "close_endpoint_m": close_endpoint,
                "precontact_pad_shell_clearance_m": precontact_values,
                "prohibited_sweeps": normalized_sweeps,
                "sha256": canonical_json_sha256(candidate),
            }
        )
    if selected not in identifiers:
        raise _error(stage, "selected_candidate_missing")
    return normalized, selected, {
        "all_prohibited_sweeps_strictly_positive": all_strictly_positive,
        "all_precontact_pad_shell_clearances_strictly_positive": (
            all_precontact_positive
        ),
        "all_required_collider_roles_covered": all_paths_covered,
    }


def evaluate_g0_clearance_certificate(certificate: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate a composed-geometry G0 certificate without issuing a command."""

    stage = "g0"
    if not isinstance(certificate, Mapping):
        raise _error(stage, "certificate_mapping_required")
    value = copy.deepcopy(dict(certificate))
    if value.get("authority") != "real_pbd_g0_clearance_certificate_v1":
        raise _error(stage, "certificate_authority_invalid")
    fixture, required_paths = _validate_g0_fixture(value.get("fixture"))
    _validate_g0_offsets(value.get("effective_offsets_m"), required_paths=required_paths)
    load = _validate_g0_load_input(value.get("load_input_authority"))
    candidates, selected, candidate_checks = _validate_g0_candidates(
        value.get("candidate_set"), required_paths=required_paths
    )
    checks = {
        "composed_fixture_complete": True,
        "effective_offsets_resolved": True,
        "finite_candidate_set": True,
        **candidate_checks,
        "runtime_filled_load_method_declared": True,
    }
    passed = all(checks.values())
    payload = {
        "authority": "real_pbd_g0_clearance_decision_v1",
        "decision": "G0_GO" if passed else "G0_NO_GO",
        "checks": checks,
        "selected_candidate_id": selected,
        "selected_candidate_sha256": next(
            item["sha256"] for item in candidates if item["id"] == selected
        ),
        "fixture_identity": {
            "usd_dependency_closure_sha256": fixture["usd_dependency_closure_sha256"],
            "composed_collision_inventory_sha256": fixture[
                "composed_collision_inventory_sha256"
            ],
        },
        "certificate_sha256": canonical_json_sha256(value),
        "g3_g4_filled_load_authorized": bool(
            load["runtime_filled_load_verified"]
        ),
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


def evaluate_static_pbd_fixture_preflight(
    *, fixture: Mapping[str, Any]
) -> dict[str, Any]:
    """Report static fixture blockers without pretending to certify runtime G0."""

    stage = "static_fixture"
    if not isinstance(fixture, Mapping):
        raise _error(stage, "fixture_invalid")
    value = copy.deepcopy(dict(fixture))
    _sha256(
        value.get("fixture_identity_sha256"), stage=stage, field="fixture_identity"
    )
    _finite_number(
        value.get("source_dry_mass_kg"),
        stage=stage,
        field="source_dry_mass",
        positive=True,
    )
    density = _finite_number(
        value.get("particle_density_kg_m3"),
        stage=stage,
        field="particle_density",
        nonnegative=True,
    )
    particle_mass = _finite_number(
        value.get("particle_mass_kg"),
        stage=stage,
        field="particle_mass",
        nonnegative=True,
    )
    particle_count = _nonnegative_index(
        value.get("particle_count"), stage=stage, field="particle_count"
    )
    wrapper_count = _nonnegative_index(
        value.get("wrapper_collider_count"), stage=stage, field="wrapper_collider_count"
    )
    expected_wrapper_count = _nonnegative_index(
        value.get("expected_wrapper_collider_count"),
        stage=stage,
        field="expected_wrapper_collider_count",
    )
    if expected_wrapper_count == 0:
        raise _error(stage, "expected_wrapper_collider_count_invalid")
    for field in (
        "runtime_cooked_geometry_available",
        "runtime_stable_particle_ids_available",
    ):
        if type(value.get(field)) is not bool:
            raise _error(stage, f"{field}_invalid")
    reasons = []
    if wrapper_count != expected_wrapper_count:
        reasons.append("wrapper_collider_inventory_mismatch")
    if particle_count == 0:
        reasons.append("particle_count_nonpositive")
    if density <= 0.0 and particle_mass <= 0.0:
        reasons.append("authored_particle_mass_and_density_nonpositive")
    if value["runtime_cooked_geometry_available"] is not True:
        reasons.append("runtime_cooked_geometry_required")
    if value["runtime_stable_particle_ids_available"] is not True:
        reasons.append("runtime_stable_particle_ids_required")
    # A static USD inspection never contains a cooked sweep witness, even if a
    # caller happens to know the runtime capability exists.  Only a later G0
    # Isaac child can issue G0_GO.
    reasons.append("runtime_signed_clearance_certificate_required")
    payload = {
        "authority": "real_pbd_static_fixture_preflight_v1",
        "fixture_identity_sha256": value["fixture_identity_sha256"],
        "particle_count": particle_count,
        "wrapper_collider_count": wrapper_count,
        "expected_wrapper_collider_count": expected_wrapper_count,
        "particle_density_kg_m3": density,
        "particle_mass_kg": particle_mass,
        "runtime_filled_payload_authority": "UNAVAILABLE_FROM_STATIC_USD",
        "g0_decision": "G0_NO_GO",
        "g2_f_prerequisites_ready": False,
        "g3_g4_filled_load_authorized": False,
        "no_go_reasons": sorted(set(reasons)),
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


_G0_RUNTIME_CAPABILITY_KEYS = frozenset(
    {
        "robot_table_cooked_geometry",
        "physx_effective_offsets",
        "signed_swept_clearance",
        "stable_particle_ids",
        "filled_load_authority",
    }
)
_G0_RUNTIME_NO_MOTION_KEYS = frozenset(
    {
        "world_constructed",
        "task_constructed",
        "controller_constructed",
        "robot_constructed",
        "world_reset_called",
        "world_step_called",
        "action_applied",
        "source_write_detected",
        "particle_write_detected",
    }
)
_G0_RUNTIME_CHILD_EXECUTION_STATUSES = frozenset(
    {"COMPLETE", "CHILD_FAILURE", "CHILD_TIMEOUT"}
)
_G0_RUNTIME_STDERR_MARKER_NAMES = frozenset(
    {
        "child_error_protocol",
        "kit_error",
        "kit_fatal",
        "native_abi_warning",
        "python_traceback",
    }
)
_G0_RUNTIME_ERROR_STDERR_MARKER_NAMES = frozenset(
    {"child_error_protocol", "kit_error", "kit_fatal", "python_traceback"}
)
_G0_RUNTIME_PROFILE_POLICY_AUTHORITY = (
    "real_pbd_g0_runtime_profile_extension_policy_v1"
)
_G0_RUNTIME_EXTENSION_CLOSURE_AUTHORITY = (
    "real_pbd_g0_runtime_extension_closure_v1"
)
_G0_RUNTIME_PROFILE_EXTENSION_EVIDENCE_AUTHORITY = (
    "real_pbd_g0_runtime_profile_extension_evidence_v1"
)
_G0_RUNTIME_EXTENSION_CAPTURE_STATUSES = frozenset(
    {"COMPLETE", "NOT_ATTEMPTED", "CAPTURE_FAILED"}
)


def _g0_runtime_extension_text(value: Any, *, field: str) -> str:
    stage = "g0_runtime_capability"
    if (
        not isinstance(value, str)
        or not value
        or any(not character.isascii() or character.isspace() for character in value)
    ):
        raise _error(stage, f"{field}_invalid")
    return value


def validate_g0_runtime_profile_extension_policy(value: Any) -> dict[str, Any]:
    """Normalize the parent-authored extension policy bound to a G0 request."""

    stage = "g0_runtime_capability"
    if not isinstance(value, Mapping):
        raise _error(stage, "profile_extension_policy_invalid")
    policy = copy.deepcopy(dict(value))
    expected = {
        "authority",
        "schema_version",
        "required_extensions",
        "forbidden_extension_names",
    }
    if (
        set(policy) != expected
        or policy.get("authority") != _G0_RUNTIME_PROFILE_POLICY_AUTHORITY
        or type(policy.get("schema_version")) is not int
        or policy["schema_version"] != 1
        or not isinstance(policy["required_extensions"], list)
        or not isinstance(policy["forbidden_extension_names"], list)
    ):
        raise _error(stage, "profile_extension_policy_invalid")
    required = []
    for record in policy["required_extensions"]:
        if not isinstance(record, Mapping) or set(record) != {"name", "version"}:
            raise _error(stage, "profile_extension_policy_invalid")
        required.append(
            {
                "name": _g0_runtime_extension_text(
                    record["name"], field="profile_extension_name"
                ),
                "version": _g0_runtime_extension_text(
                    record["version"], field="profile_extension_version"
                ),
            }
        )
    forbidden = [
        _g0_runtime_extension_text(name, field="profile_extension_name")
        for name in policy["forbidden_extension_names"]
    ]
    if (
        required != sorted(required, key=lambda record: record["name"])
        or len({record["name"] for record in required}) != len(required)
        or forbidden != sorted(forbidden)
        or len(set(forbidden)) != len(forbidden)
        or {record["name"] for record in required}.intersection(forbidden)
    ):
        raise _error(stage, "profile_extension_policy_invalid")
    return {
        "authority": _G0_RUNTIME_PROFILE_POLICY_AUTHORITY,
        "schema_version": 1,
        "required_extensions": required,
        "forbidden_extension_names": forbidden,
    }


def _g0_runtime_extension_closure(value: Any) -> dict[str, Any]:
    stage = "g0_runtime_capability"
    if not isinstance(value, Mapping):
        raise _error(stage, "profile_extension_closure_invalid")
    closure = copy.deepcopy(dict(value))
    expected = {
        "authority",
        "schema_version",
        "capture_status",
        "records",
        "closure_sha256",
    }
    if (
        set(closure) != expected
        or closure.get("authority") != _G0_RUNTIME_EXTENSION_CLOSURE_AUTHORITY
        or type(closure.get("schema_version")) is not int
        or closure["schema_version"] != 1
        or closure.get("capture_status") not in _G0_RUNTIME_EXTENSION_CAPTURE_STATUSES
    ):
        raise _error(stage, "profile_extension_closure_invalid")
    if closure["capture_status"] != "COMPLETE":
        if closure["records"] is not None or closure["closure_sha256"] is not None:
            raise _error(stage, "profile_extension_closure_invalid")
        return {
            "authority": _G0_RUNTIME_EXTENSION_CLOSURE_AUTHORITY,
            "schema_version": 1,
            "capture_status": closure["capture_status"],
            "records": None,
            "closure_sha256": None,
        }
    if not isinstance(closure["records"], list):
        raise _error(stage, "profile_extension_closure_invalid")
    records = []
    for record in closure["records"]:
        if not isinstance(record, Mapping) or set(record) != {
            "name",
            "id",
            "version",
            "path",
            "manifest_path",
            "manifest_sha256",
        }:
            raise _error(stage, "profile_extension_closure_invalid")
        path = _g0_runtime_extension_text(
            record["path"], field="profile_extension_path"
        )
        if not Path(path).is_absolute():
            raise _error(stage, "profile_extension_closure_invalid")
        manifest_path = _g0_runtime_extension_text(
            record["manifest_path"], field="profile_extension_manifest_path"
        )
        if not Path(manifest_path).is_absolute():
            raise _error(stage, "profile_extension_closure_invalid")
        records.append(
            {
                "name": _g0_runtime_extension_text(
                    record["name"], field="profile_extension_name"
                ),
                "id": _g0_runtime_extension_text(
                    record["id"], field="profile_extension_id"
                ),
                "version": _g0_runtime_extension_text(
                    record["version"], field="profile_extension_version"
                ),
                "path": path,
                "manifest_path": manifest_path,
                "manifest_sha256": _sha256(
                    record["manifest_sha256"],
                    stage=stage,
                    field="profile_extension_manifest_sha256",
                ),
            }
        )
    if (
        records != sorted(records, key=lambda record: record["id"])
        or len({record["id"] for record in records}) != len(records)
        or len({record["name"] for record in records}) != len(records)
    ):
        raise _error(stage, "profile_extension_closure_invalid")
    closure_sha256 = _sha256(
        closure["closure_sha256"], stage=stage, field="profile_extension_closure_sha256"
    )
    if closure_sha256 != canonical_json_sha256({"records": records}):
        raise _error(stage, "profile_extension_closure_invalid")
    return {
        "authority": _G0_RUNTIME_EXTENSION_CLOSURE_AUTHORITY,
        "schema_version": 1,
        "capture_status": "COMPLETE",
        "records": records,
        "closure_sha256": closure_sha256,
    }


def _g0_runtime_profile_extension_evidence(
    value: Any,
) -> tuple[dict[str, Any], bool, bool]:
    stage = "g0_runtime_capability"
    if not isinstance(value, Mapping):
        raise _error(stage, "profile_extension_evidence_invalid")
    evidence = copy.deepcopy(dict(value))
    expected = {
        "authority",
        "schema_version",
        "policy",
        "policy_sha256",
        "before_query",
        "after_query",
        "query_update_closure_sha256es",
    }
    if (
        set(evidence) != expected
        or evidence.get("authority") != _G0_RUNTIME_PROFILE_EXTENSION_EVIDENCE_AUTHORITY
        or type(evidence.get("schema_version")) is not int
        or evidence["schema_version"] != 1
        or not isinstance(evidence["query_update_closure_sha256es"], list)
    ):
        raise _error(stage, "profile_extension_evidence_invalid")
    policy = validate_g0_runtime_profile_extension_policy(evidence["policy"])
    policy_sha256 = _sha256(
        evidence["policy_sha256"], stage=stage, field="profile_extension_policy_sha256"
    )
    if policy_sha256 != canonical_json_sha256(policy):
        raise _error(stage, "profile_extension_evidence_invalid")
    before = _g0_runtime_extension_closure(evidence["before_query"])
    after = _g0_runtime_extension_closure(evidence["after_query"])
    update_hashes = [
        _sha256(value, stage=stage, field="profile_extension_update_closure_sha256")
        for value in evidence["query_update_closure_sha256es"]
    ]
    complete = bool(
        before["capture_status"] == "COMPLETE"
        and after["capture_status"] == "COMPLETE"
    )
    if not complete and update_hashes:
        raise _error(stage, "profile_extension_evidence_invalid")
    closure_unchanged = bool(
        complete
        and before["records"] == after["records"]
        and all(value == before["closure_sha256"] for value in update_hashes)
    )
    required = {record["name"]: record["version"] for record in policy["required_extensions"]}
    policy_satisfied = bool(
        complete
        and all(
            any(
                record["name"] == name and record["version"] == version
                for record in before["records"]
            )
            and any(
                record["name"] == name and record["version"] == version
                for record in after["records"]
            )
            for name, version in required.items()
        )
        and not any(
            record["name"] in policy["forbidden_extension_names"]
            for record in [*before["records"], *after["records"]]
        )
    )
    normalized = {
        "authority": _G0_RUNTIME_PROFILE_EXTENSION_EVIDENCE_AUTHORITY,
        "schema_version": 1,
        "policy": policy,
        "policy_sha256": policy_sha256,
        "before_query": before,
        "after_query": after,
        "query_update_closure_sha256es": update_hashes,
    }
    return normalized, closure_unchanged, policy_satisfied


def _g0_runtime_capability_timeline(value: Any) -> bool:
    stage = "g0_runtime_capability"
    if not isinstance(value, Mapping) or set(value) != {"before_query", "after_query"}:
        raise _error(stage, "timeline_invalid")
    timestamps = []
    for checkpoint in ("before_query", "after_query"):
        record = value[checkpoint]
        if not isinstance(record, Mapping) or set(record) != {"is_playing", "time_s"}:
            raise _error(stage, "timeline_invalid")
        if type(record["is_playing"]) is not bool:
            raise _error(stage, "timeline_invalid")
        timestamps.append(
            _finite_number(record["time_s"], stage=stage, field="timeline_time")
        )
        if record["is_playing"]:
            return False
    return bool(
        math.isclose(timestamps[0], 0.0, rel_tol=0.0, abs_tol=1.0e-12)
        and math.isclose(timestamps[1], 0.0, rel_tol=0.0, abs_tol=1.0e-12)
    )


def _g0_runtime_capability_cooked_query(
    value: Any, *, expected_paths: set[str], source_path: str
) -> tuple[bool, dict[str, Any]]:
    stage = "g0_runtime_capability"
    if not isinstance(value, Mapping):
        raise _error(stage, "cooked_invalid")
    expected_fields = {
        "status",
        "query_mode",
        "rigid_body_owner_path",
        "finished_callback_count",
        "callback_errors",
        "colliders",
        "mass_kg",
        "center_of_mass_local_m",
        "diagonal_inertia_kg_m2",
    }
    if set(value) != expected_fields:
        raise _error(stage, "cooked_invalid")
    if value["status"] not in {"COMPLETE", "FAILED", "TIMEOUT"}:
        raise _error(stage, "cooked_invalid")
    if value["query_mode"] != "QUERY_RIGID_BODY_WITH_COLLIDERS":
        raise _error(stage, "cooked_invalid")
    if _path(value["rigid_body_owner_path"], stage=stage, field="rigid_body_owner") != source_path:
        raise _error(stage, "cooked_invalid")
    finished_count = _nonnegative_index(
        value["finished_callback_count"], stage=stage, field="finished_callback_count"
    )
    errors = value["callback_errors"]
    colliders = value["colliders"]
    if (
        not isinstance(errors, Sequence)
        or isinstance(errors, (str, bytes, bytearray))
        or any(not isinstance(error, str) or not error for error in errors)
        or not isinstance(colliders, Sequence)
        or isinstance(colliders, (str, bytes, bytearray))
    ):
        raise _error(stage, "cooked_invalid")
    observed_paths = []
    normalized_colliders = []
    for record in colliders:
        if not isinstance(record, Mapping) or set(record) != {
            "path",
            "aabb_local_min_m",
            "aabb_local_max_m",
            "volume_m3",
        }:
            raise _error(stage, "cooked_invalid")
        path = _path(record["path"], stage=stage, field="cooked_collider_path")
        minimum = _finite_vector(
            record["aabb_local_min_m"], shape=(3,), stage=stage, field="cooked_aabb_min"
        )
        maximum = _finite_vector(
            record["aabb_local_max_m"], shape=(3,), stage=stage, field="cooked_aabb_max"
        )
        volume = _finite_number(
            record["volume_m3"], stage=stage, field="cooked_volume", positive=True
        )
        if np.any(minimum >= maximum):
            raise _error(stage, "cooked_invalid")
        observed_paths.append(path)
        normalized_colliders.append(
            {
                "path": path,
                "aabb_local_min_m": minimum.tolist(),
                "aabb_local_max_m": maximum.tolist(),
                "volume_m3": volume,
            }
        )
    if value["status"] == "COMPLETE":
        mass = _finite_number(value["mass_kg"], stage=stage, field="source_mass", positive=True)
        com = _finite_vector(
            value["center_of_mass_local_m"], shape=(3,), stage=stage, field="source_com"
        )
        inertia = _finite_vector(
            value["diagonal_inertia_kg_m2"], shape=(3,), stage=stage, field="source_inertia"
        )
        normalized_mass: float | None = mass
        normalized_com: list[float] | None = com.tolist()
        normalized_inertia: list[float] | None = inertia.tolist()
    elif (
        value["mass_kg"] is not None
        or value["center_of_mass_local_m"] is not None
        or value["diagonal_inertia_kg_m2"] is not None
    ):
        raise _error(stage, "cooked_invalid")
    else:
        normalized_mass = None
        normalized_com = None
        normalized_inertia = None
    unique_paths = set(observed_paths)
    complete = bool(
        value["status"] == "COMPLETE"
        and finished_count == 1
        and not errors
        and len(observed_paths) == len(unique_paths)
        and unique_paths == expected_paths
    )
    return complete, {
        "status": value["status"],
        "query_mode": value["query_mode"],
        "rigid_body_owner_path": source_path,
        "finished_callback_count": finished_count,
        "callback_errors": list(errors),
        "colliders": sorted(normalized_colliders, key=lambda item: item["path"]),
        "mass_kg": normalized_mass,
        "center_of_mass_local_m": normalized_com,
        "diagonal_inertia_kg_m2": normalized_inertia,
    }


def _g0_runtime_capability_offsets(
    value: Any, *, expected_paths: set[str]
) -> tuple[bool, list[dict[str, Any]]]:
    stage = "g0_runtime_capability"
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _error(stage, "offsets_invalid")
    normalized = []
    observed_paths = []
    for record in value:
        if not isinstance(record, Mapping) or set(record) != {
            "path",
            "contact_offset_m",
            "rest_offset_m",
            "contact_offset_authored",
            "rest_offset_authored",
        }:
            raise _error(stage, "offsets_invalid")
        path = _path(record["path"], stage=stage, field="offset_path")
        contact = record["contact_offset_m"]
        rest = record["rest_offset_m"]
        if contact is not None:
            contact = _finite_number(
                contact, stage=stage, field="authored_contact_offset", nonnegative=True
            )
        if rest is not None:
            rest = _finite_number(rest, stage=stage, field="authored_rest_offset")
        if (
            type(record["contact_offset_authored"]) is not bool
            or type(record["rest_offset_authored"]) is not bool
            or (record["contact_offset_authored"] and contact is None)
            or (record["rest_offset_authored"] and rest is None)
        ):
            raise _error(stage, "offsets_invalid")
        observed_paths.append(path)
        normalized.append(
            {
                "path": path,
                "contact_offset_m": contact,
                "rest_offset_m": rest,
                "contact_offset_authored": record["contact_offset_authored"],
                "rest_offset_authored": record["rest_offset_authored"],
            }
        )
    complete = bool(
        len(observed_paths) == len(set(observed_paths)) and set(observed_paths) == expected_paths
    )
    return complete, sorted(normalized, key=lambda item: item["path"])


def evaluate_g0_runtime_capability_audit(*, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate a read-only runtime capability snapshot; this route can never GO."""

    stage = "g0_runtime_capability"
    if not isinstance(snapshot, Mapping):
        raise _error(stage, "snapshot_mapping_required")
    value = copy.deepcopy(dict(snapshot))
    expected_fields = {
        "authority",
        "schema_version",
        "run_id",
        "parent_nonce_sha256",
        "audit_spec_sha256",
        "asset_sha256",
        "fixture_identity_sha256",
        "source_actor_path",
        "audit_status",
        "input_closure_before_sha256",
        "input_closure_after_sha256",
        "source_stage_before_sha256",
        "source_stage_after_sha256",
        "particle_stage_before_sha256",
        "particle_stage_after_sha256",
        "session_layer_before_sha256",
        "session_layer_after_sha256",
        "root_stage_before_sha256",
        "root_stage_after_sha256",
        "timeline_checkpoints",
        "no_motion_checks",
        "expected_source_collider_paths",
        "cooked_source_query",
        "authored_offsets",
        "profile_extension_evidence",
        "capability_status",
    }
    if (
        set(value) != expected_fields
        or value.get("authority") != "real_pbd_g0_runtime_capability_snapshot_v2"
        or value.get("schema_version") != 2
    ):
        raise _error(stage, "snapshot_fields_invalid")
    if not isinstance(value["run_id"], str) or not value["run_id"]:
        raise _error(stage, "run_id_invalid")
    for field in (
        "parent_nonce_sha256",
        "audit_spec_sha256",
        "asset_sha256",
        "fixture_identity_sha256",
        "input_closure_before_sha256",
        "input_closure_after_sha256",
        "source_stage_before_sha256",
        "source_stage_after_sha256",
        "particle_stage_before_sha256",
        "particle_stage_after_sha256",
        "session_layer_before_sha256",
        "session_layer_after_sha256",
        "root_stage_before_sha256",
        "root_stage_after_sha256",
    ):
        _sha256(value[field], stage=stage, field=field)
    if value["audit_status"] not in {"COMPLETE", "CHILD_FAILURE", "CHILD_TIMEOUT"}:
        raise _error(stage, "audit_status_invalid")
    source_path = _path(value["source_actor_path"], stage=stage, field="source_actor_path")
    expected_paths = _path_list(
        value["expected_source_collider_paths"], stage=stage, field="expected_source_collider_paths"
    )
    if not expected_paths:
        raise _error(stage, "expected_source_collider_paths_invalid")
    if any(not path.startswith(source_path + "/") for path in expected_paths):
        raise _error(stage, "expected_source_collider_paths_invalid")
    timeline_unchanged = _g0_runtime_capability_timeline(value["timeline_checkpoints"])
    no_motion = value["no_motion_checks"]
    if not isinstance(no_motion, Mapping) or set(no_motion) != _G0_RUNTIME_NO_MOTION_KEYS or any(
        type(result) is not bool for result in no_motion.values()
    ):
        raise _error(stage, "no_motion_checks_invalid")
    no_motion_valid = not any(no_motion.values())
    cooked_complete, cooked = _g0_runtime_capability_cooked_query(
        value["cooked_source_query"], expected_paths=set(expected_paths), source_path=source_path
    )
    offsets_complete, offsets = _g0_runtime_capability_offsets(
        value["authored_offsets"], expected_paths=set(expected_paths)
    )
    profile_extension_evidence, profile_extension_closure_unchanged, profile_extension_policy_satisfied = (
        _g0_runtime_profile_extension_evidence(value["profile_extension_evidence"])
    )
    statuses = value["capability_status"]
    if (
        not isinstance(statuses, Mapping)
        or set(statuses) != _G0_RUNTIME_CAPABILITY_KEYS
        or any(status not in {"AVAILABLE", "UNAVAILABLE"} for status in statuses.values())
    ):
        raise _error(stage, "status_invalid")
    unchanged = {
        "input_closure_unchanged": value["input_closure_before_sha256"] == value["input_closure_after_sha256"],
        "source_stage_unchanged": value["source_stage_before_sha256"] == value["source_stage_after_sha256"],
        "particle_stage_unchanged": value["particle_stage_before_sha256"] == value["particle_stage_after_sha256"],
        "session_layer_unchanged": value["session_layer_before_sha256"] == value["session_layer_after_sha256"],
        "root_stage_unchanged": value["root_stage_before_sha256"] == value["root_stage_after_sha256"],
    }
    checks = {
        "audit_completed": value["audit_status"] == "COMPLETE",
        "timeline_unchanged": timeline_unchanged,
        "no_motion": no_motion_valid,
        **unchanged,
        "source_cooked_query_complete": cooked_complete,
        "authored_offset_inventory_complete": offsets_complete,
        "profile_extension_closure_unchanged": profile_extension_closure_unchanged,
        "profile_extension_policy_satisfied": profile_extension_policy_satisfied,
    }
    reasons = []
    if not checks["audit_completed"]:
        reasons.append(f"audit_status_{str(value['audit_status']).lower()}")
    if not timeline_unchanged:
        reasons.append("timeline_changed_during_query")
    if not no_motion_valid:
        reasons.append("motion_or_write_api_observed")
    for name, valid in unchanged.items():
        if not valid:
            reasons.append(name.removesuffix("_unchanged") + "_changed")
    if not cooked_complete:
        reasons.append("source_cooked_collider_inventory_incomplete")
    if not offsets_complete:
        reasons.append("authored_offset_inventory_incomplete")
    if not profile_extension_closure_unchanged:
        reasons.append("profile_extension_closure_changed")
    if not profile_extension_policy_satisfied:
        reasons.append("profile_extension_policy_unsatisfied")
    for capability, status in sorted(statuses.items()):
        if status == "UNAVAILABLE":
            reasons.append(f"{capability}_unavailable")
    # A capability audit is deliberately incapable of turning available bits
    # into clearance authority; only the later signed-clearance issuer can GO.
    reasons.append("runtime_capability_audit_is_not_clearance_authority")
    payload = {
        "authority": "real_pbd_g0_runtime_capability_no_go_v2",
        "schema_version": 2,
        "decision": "G0_NO_GO",
        "run_id": value["run_id"],
        "parent_nonce_sha256": value["parent_nonce_sha256"],
        "audit_spec_sha256": value["audit_spec_sha256"],
        "fixture_identity_sha256": value["fixture_identity_sha256"],
        "audit_status": value["audit_status"],
        "raw_snapshot_sha256": canonical_json_sha256(value),
        "checks": checks,
        "capability_status": dict(sorted(statuses.items())),
        "source_cooked_query": cooked,
        "authored_offsets": offsets,
        "profile_extension_evidence": profile_extension_evidence,
        "no_go_reasons": sorted(set(reasons)),
        "g2_eligible": False,
        "g3_g4_filled_load_authorized": False,
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


def _g0_runtime_parent_diagnostics_valid(value: Mapping[str, Any]) -> bool:
    """Validate parent-owned child lifecycle and stderr diagnostics in G0 evidence."""

    try:
        execution = value.get("child_execution")
        if not isinstance(execution, Mapping) or set(execution) != {
            "authority",
            "schema_version",
            "parent_status",
            "returncode",
            "stderr_diagnostic",
        }:
            return False
        if (
            execution["authority"] != "real_pbd_g0_runtime_audit_child_execution_v1"
            or type(execution["schema_version"]) is not int
            or execution["schema_version"] != 1
            or execution["parent_status"] not in _G0_RUNTIME_CHILD_EXECUTION_STATUSES
        ):
            return False
        returncode = execution["returncode"]
        if returncode is not None and (
            isinstance(returncode, bool) or not isinstance(returncode, (int, np.integer))
        ):
            return False
        if execution["parent_status"] == "COMPLETE" and returncode != 0:
            return False
        diagnostic = execution["stderr_diagnostic"]
        if not isinstance(diagnostic, Mapping) or set(diagnostic) != {
            "authority",
            "schema_version",
            "stderr_sha256",
            "stderr_byte_count",
            "scanner_policy",
            "marker_line_counts",
            "runtime_log_clean",
        }:
            return False
        if (
            # v1 did not classify native ABI incompatibility warnings, so it is not sealable.
            diagnostic["authority"]
            != "real_pbd_g0_runtime_audit_stderr_diagnostic_v2"
            or type(diagnostic["schema_version"]) is not int
            or diagnostic["schema_version"] != 2
            or diagnostic["scanner_policy"]
            != "ascii_line_severity_and_native_abi_v2"
            or type(diagnostic["runtime_log_clean"]) is not bool
        ):
            return False
        _sha256(diagnostic["stderr_sha256"], stage="stage", field="child_stderr_sha256")
        _sha256(value.get("child_stdout_sha256"), stage="stage", field="child_stdout_sha256")
        _sha256(value.get("child_stderr_sha256"), stage="stage", field="child_stderr_sha256")
        if diagnostic["stderr_sha256"] != value["child_stderr_sha256"]:
            return False
        _, profile_extension_closure_unchanged, profile_extension_policy_satisfied = (
            _g0_runtime_profile_extension_evidence(
                value.get("profile_extension_evidence")
            )
        )
        receipt = value.get("runtime_receipt")
        if not isinstance(receipt, Mapping) or set(receipt) != {
            "authority",
            "schema_version",
            "parent_nonce_sha256",
            "audit_spec_sha256",
            "runtime_contract",
            "observed_runtime",
            "attestation_status",
        }:
            return False
        if (
            receipt["authority"]
            != "real_pbd_g0_runtime_capability_runtime_receipt_v1"
            or type(receipt["schema_version"]) is not int
            or receipt["schema_version"] != 1
            or receipt["parent_nonce_sha256"] != value.get("parent_nonce_sha256")
            or receipt["audit_spec_sha256"] != value.get("audit_spec_sha256")
            or receipt["attestation_status"] not in {"MATCH", "MISMATCH", "UNAVAILABLE"}
            or not isinstance(receipt["runtime_contract"], Mapping)
        ):
            return False
        contract = receipt["runtime_contract"]
        if set(contract) != {
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
        } or (
            contract.get("authority") != "real_pbd_g0_runtime_contract_v1"
            or type(contract.get("schema_version")) is not int
            or contract.get("schema_version") != 1
            or any(
                not isinstance(contract.get(field), str) or not contract[field]
                for field in (
                    "executable",
                    "prefix",
                    "python_version",
                    "isaacsim_version",
                    "numpy_version",
                    "usd_version",
                    "experience_path",
                    "experience_sha256",
                )
            )
        ):
            return False
        observed = receipt["observed_runtime"]
        if receipt["attestation_status"] == "UNAVAILABLE":
            if observed is not None:
                return False
        elif not isinstance(observed, Mapping) or set(observed) != {
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
            return False
        elif (
            any(
                not isinstance(observed.get(field), str) or not observed[field]
                for field in (
                    "executable",
                    "prefix",
                    "python_version",
                    "isaacsim_version",
                    "numpy_version",
                    "usd_version",
                    "experience_path",
                    "experience_sha256",
                )
            )
            or not isinstance(observed["module_origins"], Mapping)
            or set(observed["module_origins"])
            != {"isaacsim", "numpy", "pxr_usd", "omni_physx", "physx_bindings"}
            or any(
                not isinstance(origin, str) or not origin
                for origin in observed["module_origins"].values()
            )
        ):
            return False
        elif receipt["attestation_status"] == "MATCH" and (
            any(
                observed[field] != contract[field]
                for field in (
                    "executable",
                    "prefix",
                    "python_version",
                    "isaacsim_version",
                    "numpy_version",
                    "usd_version",
                    "experience_path",
                    "experience_sha256",
                )
            )
            or any(
                not origin.startswith(contract["prefix"].rstrip("/") + "/")
                for origin in observed["module_origins"].values()
            )
        ):
            return False
        _sha256(
            value.get("child_runtime_receipt_sha256"),
            stage="stage",
            field="child_runtime_receipt_sha256",
        )
        byte_count = diagnostic["stderr_byte_count"]
        if isinstance(byte_count, bool) or not isinstance(byte_count, (int, np.integer)) or byte_count < 0:
            return False
        counts = diagnostic["marker_line_counts"]
        if not isinstance(counts, Mapping) or set(counts) != _G0_RUNTIME_STDERR_MARKER_NAMES:
            return False
        if any(
            isinstance(count, bool) or not isinstance(count, (int, np.integer)) or count < 0
            for count in counts.values()
        ):
            return False
        runtime_log_clean = not any(counts.values())
        if diagnostic["runtime_log_clean"] is not runtime_log_clean:
            return False
        runtime_errors_observed = any(
            counts[name] for name in _G0_RUNTIME_ERROR_STDERR_MARKER_NAMES
        )
        native_abi_warning_observed = bool(counts["native_abi_warning"])
        checks = value.get("checks")
        if not isinstance(checks, Mapping) or (
            type(checks.get("child_lifecycle_clean")) is not bool
            or type(checks.get("runtime_log_clean")) is not bool
            or type(checks.get("runtime_contract_matches")) is not bool
            or type(checks.get("profile_extension_closure_unchanged")) is not bool
            or type(checks.get("profile_extension_policy_satisfied")) is not bool
        ):
            return False
        lifecycle_clean = bool(execution["parent_status"] == "COMPLETE" and returncode == 0)
        if (
            checks["child_lifecycle_clean"] is not lifecycle_clean
            or checks["runtime_log_clean"] is not runtime_log_clean
            or checks["runtime_contract_matches"] is not (
                receipt["attestation_status"] == "MATCH"
            )
            or checks["profile_extension_closure_unchanged"]
            is not profile_extension_closure_unchanged
            or checks["profile_extension_policy_satisfied"]
            is not profile_extension_policy_satisfied
        ):
            return False
        reasons = value.get("no_go_reasons")
        if not isinstance(reasons, Sequence) or isinstance(reasons, (str, bytes, bytearray)):
            return False
        if any(not isinstance(reason, str) for reason in reasons):
            return False
        return bool(
            ("child_lifecycle_not_clean" in reasons) is (not lifecycle_clean)
            and ("child_runtime_errors_observed" in reasons)
            is runtime_errors_observed
            and ("native_abi_version_incompatibility_warning_observed" in reasons)
            is native_abi_warning_observed
            and ("profile_extension_closure_changed" in reasons)
            is (not profile_extension_closure_unchanged)
            and ("profile_extension_policy_unsatisfied" in reasons)
            is (not profile_extension_policy_satisfied)
            and ("runtime_contract_mismatch" in reasons)
            is (receipt["attestation_status"] != "MATCH")
        )
    except (KeyError, TypeError, ValueError):
        return False


def _validate_g1_fixture_identity(value: Any) -> dict[str, Any]:
    stage = "g1"
    if not isinstance(value, Mapping):
        raise _error(stage, "fixture_identity_invalid")
    result = copy.deepcopy(dict(value))
    for field in (
        "usd_dependency_closure_sha256",
        "composed_collision_inventory_sha256",
        "physics_settings_sha256",
        "source_initial_pose_sha256",
    ):
        _sha256(result.get(field), stage=stage, field=field)
    _path(result.get("source_actor_path"), stage=stage, field="source_actor_path")
    _path(result.get("particle_path"), stage=stage, field="particle_path")
    return result


def _validate_g1_schedule(value: Any) -> dict[str, Any]:
    stage = "g1"
    if not isinstance(value, Mapping):
        raise _error(stage, "schedule_invalid")
    dt = _finite_number(
        value.get("physics_dt_s"), stage=stage, field="physics_dt", positive=True
    )
    pre_roll = _nonnegative_index(
        value.get("pre_roll_steps"), stage=stage, field="pre_roll_steps"
    )
    hold = _nonnegative_index(value.get("hold_steps"), stage=stage, field="hold_steps")
    if pre_roll == 0 or hold == 0:
        raise _error(stage, "schedule_invalid")
    return {
        "physics_dt_s": dt,
        "pre_roll_steps": pre_roll,
        "hold_steps": hold,
    }


def _validate_g1_treatment_mutations(
    value: Any, *, treatment: str, particle_path: str
) -> bool:
    stage = "g1"
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _error(stage, "preworld_mutations_invalid")
    mutations = [copy.deepcopy(dict(item)) for item in value if isinstance(item, Mapping)]
    if len(mutations) != len(value):
        raise _error(stage, "preworld_mutations_invalid")
    dry_mutation = {
        "phase": "pre_world",
        "operation": "set_active",
        "path": particle_path,
        "value": False,
    }
    return mutations == ([dry_mutation] if treatment == "dry" else [])


def _validate_g1_particle_authority(
    value: Any, *, treatment: str
) -> tuple[dict[str, Any], bool]:
    stage = "g1"
    if not isinstance(value, Mapping):
        raise _error(stage, "particle_authority_invalid")
    record = copy.deepcopy(dict(value))
    if treatment == "dry":
        return record, record == {"status": "NOT_APPLICABLE_BY_DRY_TREATMENT"}
    if record.get("authority") != "stable_runtime_particle_ids_v1":
        raise _error(stage, "particle_authority_invalid")
    expected_count = _nonnegative_index(
        record.get("expected_count"), stage=stage, field="particle_expected_count"
    )
    if expected_count == 0:
        raise _error(stage, "particle_expected_count_invalid")
    _sha256(record.get("stable_ids_sha256"), stage=stage, field="stable_ids")
    _sha256(
        record.get("particle_id_manifest_sha256"),
        stage=stage,
        field="particle_id_manifest",
    )
    return record, True


def _validate_g1_payload_authority(
    value: Any,
    *,
    treatment: str,
    expected_particle_count: int | None,
) -> bool:
    stage = "g1"
    if not isinstance(value, Mapping):
        raise _error(stage, "filled_payload_authority_invalid")
    if treatment == "dry":
        return value == {"status": "UNAVAILABLE"}
    if value == {"status": "UNAVAILABLE"}:
        return False
    if value.get("authority") != "runtime_filled_payload_measurement_v1":
        raise _error(stage, "filled_payload_authority_invalid")
    source_mass = _finite_number(
        value.get("source_dry_mass_kg"),
        stage=stage,
        field="source_dry_mass",
        positive=True,
    )
    particle_mass = _finite_number(
        value.get("particle_mass_kg"),
        stage=stage,
        field="particle_mass",
        nonnegative=True,
    )
    filled_mass = _finite_number(
        value.get("effective_filled_mass_kg"),
        stage=stage,
        field="effective_filled_mass",
        positive=True,
    )
    particle_count = _nonnegative_index(
        value.get("particle_count"), stage=stage, field="payload_particle_count"
    )
    gravity = _finite_vector(
        value.get("gravity_world_m_s2"), shape=(3,), stage=stage, field="payload_gravity"
    )
    if expected_particle_count is None:
        raise _error(stage, "payload_particle_authority_invalid")
    return bool(
        particle_mass > 0.0
        and filled_mass > source_mass
        and particle_count == expected_particle_count
        and float(np.linalg.norm(gravity)) > 1.0e-12
    )


def _validate_g1_records(
    value: Any,
    *,
    treatment: str,
    fixture: Mapping[str, Any],
    schedule: Mapping[str, Any],
    particle_authority: Mapping[str, Any],
) -> dict[str, Any]:
    stage = "g1"
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _error(stage, "records_invalid")
    expected_count = 1 + schedule["pre_roll_steps"] + schedule["hold_steps"]
    if len(value) != expected_count:
        raise _error(stage, "record_count_invalid")
    expected_particle_count = (
        int(particle_authority["expected_count"])
        if treatment == "filled"
        else None
    )
    stable_ids = (
        particle_authority.get("stable_ids_sha256")
        if treatment == "filled"
        else None
    )
    baseline_com = None
    baseline_pairs = None
    baseline_collision_state = None
    epoch = None
    first_world_step = None
    previous_time = None
    maximum_translation = 0.0
    maximum_tilt = 0.0
    maximum_linear_speed = 0.0
    maximum_angular_speed = 0.0
    contact_set_changes = 0
    collision_state_changes = 0
    stable_particle_coverage = True

    for index, raw_record in enumerate(value):
        if not isinstance(raw_record, Mapping):
            raise _error(stage, "record_invalid")
        record = dict(raw_record)
        record_epoch = _nonnegative_index(
            record.get("reset_epoch"), stage=stage, field="reset_epoch"
        )
        if epoch is None:
            epoch = record_epoch
        elif record_epoch != epoch:
            raise _error(stage, "reset_epoch_invalid")
        if _nonnegative_index(record.get("local_step"), stage=stage, field="local_step") != index:
            raise _error(stage, "local_step_invalid")
        world_step = _nonnegative_index(
            record.get("world_step"), stage=stage, field="world_step"
        )
        if first_world_step is None:
            first_world_step = world_step
        elif world_step != first_world_step + index:
            raise _error(stage, "world_step_invalid")
        world_time = _finite_number(
            record.get("world_time_s"), stage=stage, field="world_time"
        )
        if previous_time is not None and not math.isclose(
            world_time - previous_time,
            schedule["physics_dt_s"],
            rel_tol=0.0,
            abs_tol=1.0e-10,
        ):
            raise _error(stage, "world_time_invalid")
        previous_time = world_time
        matrix = _matrix(record.get("source_root_matrix_m"), stage=stage, field="source_root_matrix")
        pose_hash = _matrix_sha256(matrix)
        if (
            record.get("source_pose_sha256") != pose_hash
            or record.get("source_frame_pose_sha256") != pose_hash
        ):
            raise _error(stage, "source_frame_pose_stale")
        com = _finite_vector(
            record.get("source_com_position_m"), shape=(3,), stage=stage, field="source_com"
        )
        tilt = _finite_number(
            record.get("source_axis_tilt_degrees"),
            stage=stage,
            field="source_axis_tilt",
            nonnegative=True,
        )
        linear_velocity = _finite_vector(
            record.get("linear_velocity_m_s"), shape=(3,), stage=stage, field="linear_velocity"
        )
        angular_velocity = _finite_vector(
            record.get("angular_velocity_rad_s"), shape=(3,), stage=stage, field="angular_velocity"
        )
        if record.get("collision_inventory_sha256") != fixture[
            "composed_collision_inventory_sha256"
        ]:
            raise _error(stage, "collision_inventory_changed")
        collision_state = _sha256(
            record.get("collision_state_sha256"), stage=stage, field="collision_state"
        )
        contact_pairs_raw = record.get("contact_pairs")
        if not isinstance(contact_pairs_raw, Sequence) or isinstance(
            contact_pairs_raw, (str, bytes, bytearray)
        ):
            raise _error(stage, "contact_pairs_invalid")
        contact_pairs = {_pair(pair, stage=stage, field="contact_pair") for pair in contact_pairs_raw}
        if len(contact_pairs) != len(contact_pairs_raw):
            raise _error(stage, "contact_pairs_invalid")
        if baseline_com is None:
            baseline_com = com
            baseline_pairs = contact_pairs
            baseline_collision_state = collision_state
        else:
            contact_set_changes += int(contact_pairs != baseline_pairs)
            collision_state_changes += int(collision_state != baseline_collision_state)
        maximum_translation = max(
            maximum_translation, float(np.linalg.norm(com - baseline_com))
        )
        maximum_tilt = max(maximum_tilt, tilt)
        maximum_linear_speed = max(maximum_linear_speed, float(np.linalg.norm(linear_velocity)))
        maximum_angular_speed = max(
            maximum_angular_speed, float(np.linalg.norm(angular_velocity))
        )

        particle_fields = {
            "particle_count",
            "particle_ids_sha256",
            "particle_id_coverage_count",
            "particle_positions_sha256",
        }
        if treatment == "filled":
            particle_count = _nonnegative_index(
                record.get("particle_count"), stage=stage, field="particle_count"
            )
            coverage_count = _nonnegative_index(
                record.get("particle_id_coverage_count"),
                stage=stage,
                field="particle_id_coverage_count",
            )
            ids = _sha256(
                record.get("particle_ids_sha256"), stage=stage, field="particle_ids"
            )
            _sha256(
                record.get("particle_positions_sha256"),
                stage=stage,
                field="particle_positions",
            )
            stable_particle_coverage = bool(
                stable_particle_coverage
                and particle_count == expected_particle_count
                and coverage_count == expected_particle_count
                and ids == stable_ids
            )
        elif particle_fields & set(record):
            raise _error(stage, "dry_particle_readback_forbidden")

    return {
        "maximum_translation_m": maximum_translation,
        "maximum_tilt_degrees": maximum_tilt,
        "maximum_linear_speed_m_s": maximum_linear_speed,
        "maximum_angular_speed_rad_s": maximum_angular_speed,
        "contact_set_changes": contact_set_changes,
        "collision_state_changes": collision_state_changes,
        "stable_particle_coverage": stable_particle_coverage,
        "record_count": expected_count,
    }


def _validate_g1_report(value: Any, *, expected_treatment: str) -> dict[str, Any]:
    stage = "g1"
    if not isinstance(value, Mapping):
        raise _error(stage, "report_mapping_required")
    report = copy.deepcopy(dict(value))
    if (
        report.get("authority") != "real_pbd_g1_passive_baseline_v1"
        or report.get("treatment") != expected_treatment
    ):
        raise _error(stage, "report_identity_invalid")
    fixture = _validate_g1_fixture_identity(report.get("fixture_identity"))
    schedule = _validate_g1_schedule(report.get("schedule"))
    treatment_valid = _validate_g1_treatment_mutations(
        report.get("preworld_mutations"),
        treatment=expected_treatment,
        particle_path=fixture["particle_path"],
    )
    particle_authority, particle_authority_valid = _validate_g1_particle_authority(
        report.get("particle_authority"), treatment=expected_treatment
    )
    metrics = _validate_g1_records(
        report.get("records"),
        treatment=expected_treatment,
        fixture=fixture,
        schedule=schedule,
        particle_authority=particle_authority,
    )
    payload_valid = _validate_g1_payload_authority(
        report.get("filled_payload_authority"),
        treatment=expected_treatment,
        expected_particle_count=(
            int(particle_authority["expected_count"])
            if expected_treatment == "filled"
            else None
        ),
    )
    return {
        "fixture": fixture,
        "schedule": schedule,
        "treatment_valid": treatment_valid,
        "particle_authority_valid": particle_authority_valid,
        "payload_valid": payload_valid,
        "metrics": metrics,
    }


def _validate_g1_limits(value: Any) -> dict[str, float | int]:
    stage = "g1"
    if not isinstance(value, Mapping):
        raise _error(stage, "limits_invalid")
    number_fields = (
        "maximum_translation_m",
        "maximum_tilt_degrees",
        "maximum_linear_speed_m_s",
        "maximum_angular_speed_rad_s",
        "maximum_differential_translation_m",
        "maximum_differential_tilt_degrees",
        "maximum_differential_linear_speed_m_s",
        "maximum_differential_angular_speed_rad_s",
    )
    result: dict[str, float | int] = {
        field: _finite_number(
            value.get(field), stage=stage, field=field, nonnegative=True
        )
        for field in number_fields
    }
    for field in (
        "maximum_contact_set_changes",
        "maximum_collision_state_changes",
    ):
        result[field] = _nonnegative_index(value.get(field), stage=stage, field=field)
    return result


def _g1_own_bounds(metrics: Mapping[str, Any], limits: Mapping[str, Any]) -> bool:
    return bool(
        metrics["maximum_translation_m"] <= limits["maximum_translation_m"]
        and metrics["maximum_tilt_degrees"] <= limits["maximum_tilt_degrees"]
        and metrics["maximum_linear_speed_m_s"] <= limits["maximum_linear_speed_m_s"]
        and metrics["maximum_angular_speed_rad_s"]
        <= limits["maximum_angular_speed_rad_s"]
        and metrics["contact_set_changes"] <= limits["maximum_contact_set_changes"]
        and metrics["collision_state_changes"]
        <= limits["maximum_collision_state_changes"]
    )


def evaluate_g1_treatment(
    *, report: Mapping[str, Any], limits: Mapping[str, Any]
) -> dict[str, Any]:
    """Evaluate one fresh G1-D or G1-F child before pair comparison."""

    if not isinstance(report, Mapping) or report.get("treatment") not in {
        "dry",
        "filled",
    }:
        raise _error("g1", "treatment_invalid")
    treatment = str(report["treatment"])
    normalized = _validate_g1_report(report, expected_treatment=treatment)
    bounds = _validate_g1_limits(limits)
    checks = {
        "treatment_preworld_mutation": normalized["treatment_valid"],
        "trace_bounds": _g1_own_bounds(normalized["metrics"], bounds),
        "stable_particle_id_coverage": (
            True
            if treatment == "dry"
            else bool(
                normalized["particle_authority_valid"]
                and normalized["metrics"]["stable_particle_coverage"]
            )
        ),
    }
    g2_eligible = all(checks.values())
    payload = {
        "authority": "real_pbd_g1_treatment_decision_v1",
        "treatment": treatment,
        "decision": (
            "G1_D_GO"
            if treatment == "dry" and g2_eligible
            else "G1_F_GO"
            if treatment == "filled" and g2_eligible
            else "G1_D_NO_GO"
            if treatment == "dry"
            else "G1_F_NO_GO"
        ),
        "checks": checks,
        "metrics": normalized["metrics"],
        "fixture_identity_sha256": canonical_json_sha256(normalized["fixture"]),
        "fixture_lineage_sha256": canonical_json_sha256(
            {
                "usd_dependency_closure_sha256": normalized["fixture"]["usd_dependency_closure_sha256"],
                "composed_collision_inventory_sha256": normalized["fixture"]["composed_collision_inventory_sha256"],
            }
        ),
        "g2_eligible": g2_eligible,
        "g3_g4_filled_load_authorized": bool(
            treatment == "filled" and g2_eligible and normalized["payload_valid"]
        ),
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


def evaluate_g1_baseline_pair(
    *,
    dry_report: Mapping[str, Any],
    filled_report: Mapping[str, Any],
    limits: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare same-fixture dry and filled passive holds for G1."""

    dry = _validate_g1_report(dry_report, expected_treatment="dry")
    filled = _validate_g1_report(filled_report, expected_treatment="filled")
    bounds = _validate_g1_limits(limits)
    same_fixture = dry["fixture"] == filled["fixture"]
    same_schedule = dry["schedule"] == filled["schedule"]
    dry_bounds = _g1_own_bounds(dry["metrics"], bounds)
    filled_bounds = _g1_own_bounds(filled["metrics"], bounds)
    differential = {
        "translation_m": abs(
            dry["metrics"]["maximum_translation_m"]
            - filled["metrics"]["maximum_translation_m"]
        ),
        "tilt_degrees": abs(
            dry["metrics"]["maximum_tilt_degrees"]
            - filled["metrics"]["maximum_tilt_degrees"]
        ),
        "linear_speed_m_s": abs(
            dry["metrics"]["maximum_linear_speed_m_s"]
            - filled["metrics"]["maximum_linear_speed_m_s"]
        ),
        "angular_speed_rad_s": abs(
            dry["metrics"]["maximum_angular_speed_rad_s"]
            - filled["metrics"]["maximum_angular_speed_rad_s"]
        ),
    }
    differential_valid = bool(
        differential["translation_m"] <= bounds["maximum_differential_translation_m"]
        and differential["tilt_degrees"] <= bounds["maximum_differential_tilt_degrees"]
        and differential["linear_speed_m_s"]
        <= bounds["maximum_differential_linear_speed_m_s"]
        and differential["angular_speed_rad_s"]
        <= bounds["maximum_differential_angular_speed_rad_s"]
    )
    checks = {
        "same_fixture_identity": same_fixture,
        "same_schedule": same_schedule,
        "dry_only_preworld_mutation": dry["treatment_valid"],
        "filled_no_preworld_mutation": filled["treatment_valid"],
        "dry_trace_bounds": dry_bounds,
        "filled_trace_bounds": filled_bounds,
        "stable_particle_id_coverage": bool(
            filled["particle_authority_valid"]
            and filled["metrics"]["stable_particle_coverage"]
        ),
        "differential_bounds": differential_valid,
    }
    g2_authorized = all(checks.values())
    payload_authorized = bool(g2_authorized and filled["payload_valid"])
    payload = {
        "authority": "real_pbd_g1_baseline_comparison_v1",
        "decision": "G1_GO" if g2_authorized else "G1_NO_GO",
        "checks": checks,
        "dry_metrics": dry["metrics"],
        "filled_metrics": filled["metrics"],
        "differential": differential,
        "fixture_identity_sha256": canonical_json_sha256(dry["fixture"]),
        "fixture_lineage_sha256": canonical_json_sha256(
            {
                "usd_dependency_closure_sha256": dry["fixture"]["usd_dependency_closure_sha256"],
                "composed_collision_inventory_sha256": dry["fixture"]["composed_collision_inventory_sha256"],
            }
        ),
        "g2_f_authorized": g2_authorized,
        "g3_g4_filled_load_authorized": payload_authorized,
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


def _legacy_build_g2_immediate_report_envelope(
    raw_physx_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Wrap one unfiltered immediate PhysX report in the v2 hashed envelope."""

    stage = "g2"
    if not isinstance(raw_physx_report, Mapping):
        raise _error(stage, "immediate_report_invalid")
    raw = copy.deepcopy(dict(raw_physx_report))
    if raw.get("authority") != "physx_immediate_full_contact_report_v1":
        raise _error(stage, "immediate_report_invalid")
    physics_index = _nonnegative_index(
        raw.get("physics_index"), stage=stage, field="immediate_physics_index"
    )
    for field in (
        "header_count",
        "contact_data_count",
        "friction_anchor_count",
        "occurrence_count",
        "current_pair_count",
        "bootstrap_pair_count",
        "immediate_read_index",
        "immediate_read_count",
    ):
        _nonnegative_index(raw.get(field), stage=stage, field=field)
    if (
        raw["range_partition_valid"] is not True
        or raw["immediate_read_count"] != raw["immediate_read_index"] + 1
    ):
        raise _error(stage, "immediate_report_invalid")
    raw_headers = raw.get("raw_headers")
    raw_contacts = raw.get("raw_contact_data")
    raw_friction = raw.get("raw_friction_anchors")
    if (
        not isinstance(raw_headers, Sequence)
        or isinstance(raw_headers, (str, bytes, bytearray))
        or not isinstance(raw_contacts, Sequence)
        or isinstance(raw_contacts, (str, bytes, bytearray))
        or not isinstance(raw_friction, Sequence)
        or isinstance(raw_friction, (str, bytes, bytearray))
        or any(not isinstance(item, Mapping) for item in raw_headers)
        or any(not isinstance(item, Mapping) for item in raw_contacts)
        or any(not isinstance(item, Mapping) for item in raw_friction)
        or raw["header_count"] != len(raw_headers)
        or raw["contact_data_count"] != len(raw_contacts)
        or raw["friction_anchor_count"] != len(raw_friction)
    ):
        raise _error(stage, "immediate_report_invalid")
    contact_used = [False] * len(raw_contacts)
    friction_used = [False] * len(raw_friction)
    header_groups: dict[tuple[tuple[str, int], tuple[str, int]], dict[str, Any]] = {}
    for header_value in raw_headers:
        header = copy.deepcopy(dict(header_value))
        event = header.get("type")
        if event not in {"FOUND", "PERSIST", "LOST"}:
            raise _error(stage, "immediate_report_invalid")
        pair_identity = _g2_sealed_raw_pair(
            [
                {
                    "collider_path": header.get("collider0"),
                    "proto_index": header.get("proto_index0"),
                },
                {
                    "collider_path": header.get("collider1"),
                    "proto_index": header.get("proto_index1"),
                },
            ],
            field="raw_header_pair",
        )
        ranges = []
        for offset_field, count_field, used in (
            ("contact_data_offset", "num_contact_data", contact_used),
            ("friction_anchors_offset", "num_friction_anchors_data", friction_used),
        ):
            offset = _nonnegative_index(header.get(offset_field), stage=stage, field=offset_field)
            count = _nonnegative_index(header.get(count_field), stage=stage, field=count_field)
            if offset + count > len(used) or any(used[offset : offset + count]):
                raise _error(stage, "immediate_report_invalid")
            for index in range(offset, offset + count):
                used[index] = True
            ranges.append((offset, count))
        contact_offset, contact_count = ranges[0]
        friction_offset, friction_count = ranges[1]
        group = header_groups.setdefault(
            pair_identity,
            {"headers": [], "contact_data": [], "friction_anchors": [], "fragments": []},
        )
        group["headers"].append(header)
        group["contact_data"].extend(
            copy.deepcopy(raw_contacts[index])
            for index in range(contact_offset, contact_offset + contact_count)
        )
        group["friction_anchors"].extend(
            copy.deepcopy(raw_friction[index])
            for index in range(friction_offset, friction_offset + friction_count)
        )
        group["fragments"].append(
            {
                "header": copy.deepcopy(header),
                "contact_data": [
                    copy.deepcopy(raw_contacts[index])
                    for index in range(contact_offset, contact_offset + contact_count)
                ],
                "friction_anchors": [
                    copy.deepcopy(raw_friction[index])
                    for index in range(friction_offset, friction_offset + friction_count)
                ],
            }
        )
    if not all(contact_used) or not all(friction_used):
        raise _error(stage, "immediate_report_invalid")
    if Counter(event_sequences) != Counter(
        ",".join(header["type"] for header in group["headers"])
        for group in header_groups.values()
    ):
        raise _error(stage, "immediate_report_invalid")
    event_sequences = raw.get("event_sequences")
    occurrences = raw.get("occurrences")
    if (
        not isinstance(event_sequences, Sequence)
        or isinstance(event_sequences, (str, bytes, bytearray))
        or any(not isinstance(item, str) or not item for item in event_sequences)
        or not isinstance(occurrences, Sequence)
        or isinstance(occurrences, (str, bytes, bytearray))
        or raw["occurrence_count"] != len(occurrences)
    ):
        raise _error(stage, "immediate_report_invalid")
    for occurrence in occurrences:
        if not isinstance(occurrence, Mapping):
            raise _error(stage, "immediate_report_invalid")
        fragments = occurrence.get("fragments")
        if (
            not isinstance(fragments, Sequence)
            or isinstance(fragments, (str, bytes, bytearray))
            or not fragments
        ):
            raise _error(stage, "immediate_report_invalid")
    current_pairs = _raw_current_pairs(raw)
    if raw["current_pair_count"] != len(current_pairs):
        raise _error(stage, "immediate_report_invalid")
    payload = {
        "authority": "full_contact_report_step_v1",
        "physics_index": physics_index,
        "current_pairs": copy.deepcopy(raw["current_pairs"]),
        "occurrences": copy.deepcopy(raw["occurrences"]),
        "raw_physx_report": raw,
        "raw_physx_report_sha256": canonical_json_sha256(raw),
    }
    return {**payload, "evidence_sha256": canonical_json_sha256(payload)}


def _legacy_build_g2_sensor_pair_receipt(
    *, physics_step: int, normalized_sensor_contacts: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Seal same-step sensor pairs as a cross-check, never as grasp authority."""

    stage = "g2"
    expected_step = _nonnegative_index(
        physics_step, stage=stage, field="sensor_physics_step"
    )
    if not isinstance(normalized_sensor_contacts, Sequence) or isinstance(
        normalized_sensor_contacts, (str, bytes, bytearray)
    ):
        raise _error(stage, "sensor_receipt_invalid")
    contacts = []
    pairs: set[tuple[str, str]] = set()
    for contact in normalized_sensor_contacts:
        if not isinstance(contact, Mapping) or contact.get("physics_step") != expected_step:
            raise _error(stage, "sensor_receipt_invalid")
        pair = _pair(
            [contact.get("collider0_path"), contact.get("collider1_path")],
            stage=stage,
            field="sensor_pair",
        )
        pairs.add(pair)
        contacts.append(copy.deepcopy(dict(contact)))
    payload = {
        "authority": "real_pbd_g2_sensor_pair_receipt_v1",
        "physics_step": expected_step,
        "pairs": [list(pair) for pair in sorted(pairs)],
        "normalized_sensor_contacts": contacts,
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


def _raw_current_pairs(value: Mapping[str, Any]) -> set[tuple[str, str]]:
    stage = "g2"
    raw_pairs = value.get("current_pairs")
    if not isinstance(raw_pairs, Sequence) or isinstance(
        raw_pairs, (str, bytes, bytearray)
    ):
        raise _error(stage, "current_pairs_invalid")
    result: set[tuple[str, str]] = set()
    for raw_pair in raw_pairs:
        if not isinstance(raw_pair, Sequence) or isinstance(
            raw_pair, (str, bytes, bytearray)
        ) or len(raw_pair) != 2:
            raise _error(stage, "current_pairs_invalid")
        paths = []
        for endpoint in raw_pair:
            if not isinstance(endpoint, Mapping):
                raise _error(stage, "current_pairs_invalid")
            paths.append(_path(endpoint.get("collider_path"), stage=stage, field="collider_path"))
            proto = endpoint.get("proto_index")
            if (
                isinstance(proto, bool)
                or not isinstance(proto, (int, np.integer))
                or not 0 <= int(proto) <= 0xFFFFFFFF
            ):
                raise _error(stage, "current_pairs_invalid")
        pair = tuple(sorted(paths))
        if pair[0] == pair[1] or pair in result:
            raise _error(stage, "current_pairs_invalid")
        result.add(pair)
    return result


def _classification_records(
    value: Mapping[str, Any], *, raw_pairs: set[tuple[str, str]]
) -> tuple[dict[tuple[str, str], dict[str, Any]], str | None, bool]:
    stage = "g2"
    records = value.get("records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)):
        raise _error(stage, "classification_records_invalid")
    normalized: dict[tuple[str, str], dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    transient_intended = False
    for raw in records:
        if not isinstance(raw, Mapping):
            raise _error(stage, "classification_records_invalid")
        contact_class = raw.get("class")
        if contact_class not in _CONTACT_CLASSES:
            raise _error(stage, "classification_records_invalid")
        pair_value = raw.get("pair")
        if not isinstance(pair_value, Mapping):
            raise _error(stage, "classification_records_invalid")
        pair = _pair(pair_value.get("collider_paths"), stage=stage, field="classification_pair")
        if pair in normalized:
            raise _error(stage, "classification_records_invalid")
        side = raw.get("side")
        if side is not None and side not in {"left", "right"}:
            raise _error(stage, "classification_records_invalid")
        current = raw.get("current")
        transient = raw.get("transient")
        if type(current) is not bool or type(transient) is not bool:
            raise _error(stage, "classification_records_invalid")
        failures = raw.get("gate_failures")
        if not isinstance(failures, Sequence) or isinstance(
            failures, (str, bytes, bytearray)
        ) or any(not isinstance(item, str) for item in failures):
            raise _error(stage, "classification_records_invalid")
        if current and pair not in raw_pairs:
            raise _error(stage, "classification_current_pair_invalid")
        if not current and not transient:
            raise _error(stage, "classification_lifecycle_invalid")
        if transient and contact_class in {
            "INTENDED_PRECONTACT",
            "INTENDED_CLOSE_CONTACT",
        }:
            transient_intended = True
        normalized[pair] = {
            "class": contact_class,
            "side": side,
            "current": current,
            "transient": transient,
        }
        counts[contact_class] += 1
    if value.get("class_counts") != dict(sorted(counts.items())):
        raise _error(stage, "classification_counts_invalid")
    terminal = value.get("terminal_kind")
    if terminal not in {
        None,
        "PROTOCOL_FAILURE",
        "PHYSICAL_CONTACT_FAILURE",
        "PHYSICAL_MOTION_FAILURE",
    }:
        raise _error(stage, "classification_terminal_invalid")
    if type(value.get("source_motion_authority_valid")) is not bool:
        raise _error(stage, "classification_source_motion_authority_invalid")
    expected_terminal = (
        "PROTOCOL_FAILURE"
        if counts.get("UNKNOWN_CONTACT", 0)
        or value["source_motion_authority_valid"] is False
        else "PHYSICAL_CONTACT_FAILURE"
        if counts.get("PROHIBITED_CONTACT", 0)
        else None
    )
    if expected_terminal is not None and terminal != expected_terminal:
        raise _error(stage, "classification_terminal_invalid")
    return normalized, terminal, transient_intended


def _validate_g2_source_state(value: Any, *, physics_step: int) -> None:
    stage = "g2"
    if not isinstance(value, Mapping) or value.get("physics_step") != physics_step:
        raise _error(stage, "source_state_receipt_invalid")
    for boundary in ("pre", "post"):
        state = value.get(boundary)
        if not isinstance(state, Mapping):
            raise _error(stage, "source_state_receipt_invalid")
        _finite_vector(
            state.get("com_position_m"), shape=(3,), stage=stage, field="source_com"
        )
        _finite_vector(
            state.get("orientation_wxyz"),
            shape=(4,),
            stage=stage,
            field="source_orientation",
            unit=True,
        )
        _finite_vector(
            state.get("linear_velocity_m_s"),
            shape=(3,),
            stage=stage,
            field="source_linear_velocity",
        )
        _finite_vector(
            state.get("angular_velocity_rad_s"),
            shape=(3,),
            stage=stage,
            field="source_angular_velocity",
        )


def _validate_g2_action_receipt(value: Any, *, phase: str) -> str:
    stage = "g2"
    if not isinstance(value, Mapping):
        raise _error(stage, "action_receipt_invalid")
    if (
        value.get("authority") != "controlled_action_applied_receipt_v1"
        or value.get("phase") != phase
        or value.get("semantic_action_kind") not in _G2_ACTION_KINDS[phase]
        or value.get("physics_steps_before_receipt") != 0
    ):
        raise _error(stage, "action_receipt_invalid")
    _sha256(value.get("action_sha256"), stage=stage, field="action")
    _sha256(value.get("target_token_sha256"), stage=stage, field="target_token")
    return canonical_json_sha256(dict(value))


def _sensor_pairs(value: Any) -> set[tuple[str, str]]:
    stage = "g2"
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _error(stage, "sensor_pairs_invalid")
    pairs = {_pair(item, stage=stage, field="sensor_pair") for item in value}
    if len(pairs) != len(value):
        raise _error(stage, "sensor_pairs_invalid")
    return pairs


def _legacy_evaluate_g2_substep(
    *,
    phase: str,
    interval_index: int,
    substep_slot: int,
    substeps_per_interval: int,
    immediate_report: Mapping[str, Any],
    classification: Mapping[str, Any],
    expected_baseline_pairs: Sequence[Sequence[str]],
    intended_finger_pairs: Mapping[str, Sequence[str]],
    source_wrapper_collider_paths: Sequence[str],
    particle_collider_paths: Sequence[str],
    sensor_current_pairs: Sequence[Sequence[str]],
    source_state_receipt: Mapping[str, Any],
    action_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate one G2 substep using immediate PhysX evidence as authority."""

    stage = "g2"
    if phase not in _G2_PHASES:
        raise _error(stage, "phase_invalid")
    interval = _nonnegative_index(interval_index, stage=stage, field="interval_index")
    slot = _nonnegative_index(substep_slot, stage=stage, field="substep_slot")
    total_slots = _nonnegative_index(
        substeps_per_interval, stage=stage, field="substeps_per_interval"
    )
    if total_slots == 0 or slot == 0 or slot > total_slots:
        raise _error(stage, "substep_slot_invalid")
    raw = _hash_checked_mapping(
        immediate_report,
        stage=stage,
        authority="full_contact_report_step_v1",
    )
    physics_step = _nonnegative_index(
        raw.get("physics_index"), stage=stage, field="physics_index"
    )
    raw_pairs = _raw_current_pairs(raw)
    classified = _hash_checked_mapping(
        classification,
        stage=stage,
        authority="controlled_contact_complete_immediate_report_v1",
    )
    if (
        classified.get("physics_step") != physics_step
        or classified.get("phase") != phase
    ):
        raise _error(stage, "classification_identity_invalid")
    records, classified_terminal, transient_intended = _classification_records(
        classified, raw_pairs=raw_pairs
    )
    baseline_pairs = {
        _pair(value, stage=stage, field="baseline_pair")
        for value in expected_baseline_pairs
    }
    if len(baseline_pairs) != len(expected_baseline_pairs):
        raise _error(stage, "baseline_pairs_invalid")
    if not isinstance(intended_finger_pairs, Mapping) or set(intended_finger_pairs) != {
        "left",
        "right",
    }:
        raise _error(stage, "intended_finger_pairs_invalid")
    intended_pairs = {
        side: _pair(value, stage=stage, field=f"{side}_intended_pair")
        for side, value in intended_finger_pairs.items()
    }
    if len(set(intended_pairs.values())) != 2:
        raise _error(stage, "intended_finger_pairs_invalid")
    source_colliders = set(intended_pairs["left"]) & set(intended_pairs["right"])
    if len(source_colliders) != 1:
        raise _error(stage, "intended_finger_pairs_invalid")
    finger_colliders = (
        set(intended_pairs["left"]) | set(intended_pairs["right"])
    ) - source_colliders
    if len(finger_colliders) != 2:
        raise _error(stage, "intended_finger_pairs_invalid")
    wrappers = set(
        _path_list(
            source_wrapper_collider_paths,
            stage=stage,
            field="source_wrapper_collider_paths",
        )
    )
    particles = set(
        _path_list(
            particle_collider_paths,
            stage=stage,
            field="particle_collider_paths",
        )
    )
    sensors = _sensor_pairs(sensor_current_pairs)
    _validate_g2_source_state(source_state_receipt, physics_step=physics_step)
    action_receipt_sha256 = _validate_g2_action_receipt(action_receipt, phase=phase)

    protocol_failures: set[str] = set()
    physical_failures: set[str] = set()
    if classified_terminal == "PROTOCOL_FAILURE":
        protocol_failures.add("classification_protocol_terminal")
    elif classified_terminal in {"PHYSICAL_CONTACT_FAILURE", "PHYSICAL_MOTION_FAILURE"}:
        physical_failures.add("classification_physical_terminal")
    if transient_intended:
        physical_failures.add("transient_intended_contact")

    active_background = set()
    active_intended: dict[str, tuple[str, str]] = {}
    for pair in raw_pairs:
        record = records.get(pair)
        if record is None or record["current"] is not True:
            protocol_failures.add("immediate_pair_classification_gap")
            continue
        if set(pair) & (wrappers | particles):
            physical_failures.add("wrapper_or_particle_contact")
        if pair in baseline_pairs:
            active_background.add(pair)
            if record["class"] != "BACKGROUND":
                protocol_failures.add("baseline_classification_mismatch")
            continue
        intended_side = next(
            (side for side, intended in intended_pairs.items() if pair == intended), None
        )
        if intended_side is None:
            physical_failures.add("unexpected_current_pair")
            continue
        active_intended[intended_side] = pair
        expected_class = (
            "INTENDED_PRECONTACT"
            if phase in _G2_PRECONTACT_PHASES
            else "INTENDED_CLOSE_CONTACT"
            if phase in _G2_CLOSE_PHASES
            else None
        )
        if expected_class is None:
            physical_failures.add("contact_outside_contact_phase")
        elif record["class"] != expected_class or record["side"] != intended_side:
            physical_failures.add("intended_contact_classification_mismatch")

    if active_background != baseline_pairs:
        physical_failures.add("baseline_contact_changed")
    # Sensors are cross-checks for every current pad contact, including an
    # illegal pad-to-wrapper contact.  Comparing only intended pairs would turn
    # a physically observed wrapper breach into a misleading sensor protocol
    # mismatch even when both instruments agree on the bad contact.
    expected_sensor_pairs = {
        pair for pair in raw_pairs if set(pair) & finger_colliders
    }
    if sensors != expected_sensor_pairs:
        protocol_failures.add("sensor_immediate_disagreement")

    terminal_kind = (
        "PROTOCOL_FAILURE"
        if protocol_failures
        else "PHYSICAL_CONTACT_FAILURE"
        if physical_failures
        else None
    )
    payload = {
        "authority": "real_pbd_g2_substep_decision_v1",
        "physics_step": physics_step,
        "interval_index": interval,
        "substep_slot": slot,
        "substeps_per_interval": total_slots,
        "phase": phase,
        "raw_immediate_report_sha256": raw["evidence_sha256"],
        "classification_evidence_sha256": classified["evidence_sha256"],
        "action_receipt_sha256": action_receipt_sha256,
        "source_state_receipt_sha256": canonical_json_sha256(dict(source_state_receipt)),
        "current_intended_sides": sorted(active_intended),
        "terminal_kind": terminal_kind,
        "protocol_failures": sorted(protocol_failures),
        "physical_failures": sorted(physical_failures),
        "remaining_substeps_allowed": terminal_kind is None,
        "next_action_allowed": terminal_kind is None,
        # A G2 certificate is launch evidence for a later fresh G3 child only.
        # It never permits a lift or pour in this child.
        "lift_allowed": False,
        "pour_allowed": False,
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


# The public G2 entry points below deliberately replace the early v2 draft
# above.  The draft accepted independently caller-authored contact and role
# maps; the sealed route binds every substep to one launch context instead.
def _g2_sealed_pair(value: Any, *, field: str) -> tuple[str, str]:
    return _pair(value, stage="g2", field=field)


def _g2_sealed_raw_pair(value: Any, *, field: str) -> tuple[tuple[str, int], tuple[str, int]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or len(value) != 2:
        raise _error("g2", f"{field}_invalid")
    endpoints = []
    for endpoint in value:
        if not isinstance(endpoint, Mapping):
            raise _error("g2", f"{field}_invalid")
        path = _path(endpoint.get("collider_path"), stage="g2", field=field)
        proto = endpoint.get("proto_index")
        if isinstance(proto, bool) or not isinstance(proto, (int, np.integer)) or not 0 <= int(proto) <= 0xFFFFFFFF:
            raise _error("g2", f"{field}_invalid")
        endpoints.append((path, int(proto)))
    result = tuple(sorted(endpoints))
    if result[0][0] == result[1][0]:
        raise _error("g2", f"{field}_invalid")
    return result


def _g2_sealed_path_pair(value: tuple[tuple[str, int], tuple[str, int]]) -> tuple[str, str]:
    return tuple(sorted((value[0][0], value[1][0])))


def _g2_sealed_raw_header_groups(
    raw: Mapping[str, Any], event_sequences: Sequence[str]
) -> dict[tuple[tuple[str, int], tuple[str, int]], dict[str, Any]]:
    """Reconstruct every raw pair from the complete PhysX buffer."""

    stage = "g2"
    raw_headers = raw.get("raw_headers")
    raw_contacts = raw.get("raw_contact_data")
    raw_friction = raw.get("raw_friction_anchors")
    if (
        not isinstance(raw_headers, Sequence)
        or isinstance(raw_headers, (str, bytes, bytearray))
        or not isinstance(raw_contacts, Sequence)
        or isinstance(raw_contacts, (str, bytes, bytearray))
        or not isinstance(raw_friction, Sequence)
        or isinstance(raw_friction, (str, bytes, bytearray))
        or any(not isinstance(item, Mapping) for item in raw_headers)
        or any(not isinstance(item, Mapping) for item in raw_contacts)
        or any(not isinstance(item, Mapping) for item in raw_friction)
        or raw["header_count"] != len(raw_headers)
        or raw["contact_data_count"] != len(raw_contacts)
        or raw["friction_anchor_count"] != len(raw_friction)
    ):
        raise _error(stage, "immediate_report_invalid")
    contact_used = [False] * len(raw_contacts)
    friction_used = [False] * len(raw_friction)
    groups: dict[tuple[tuple[str, int], tuple[str, int]], dict[str, Any]] = {}
    for header_value in raw_headers:
        header = copy.deepcopy(dict(header_value))
        if header.get("type") not in {"FOUND", "PERSIST", "LOST"}:
            raise _error(stage, "immediate_report_invalid")
        pair_identity = _g2_sealed_raw_pair(
            [
                {
                    "collider_path": header.get("collider0"),
                    "proto_index": header.get("proto_index0"),
                },
                {
                    "collider_path": header.get("collider1"),
                    "proto_index": header.get("proto_index1"),
                },
            ],
            field="raw_header_pair",
        )
        ranges = []
        for offset_field, count_field, used in (
            ("contact_data_offset", "num_contact_data", contact_used),
            ("friction_anchors_offset", "num_friction_anchors_data", friction_used),
        ):
            offset = _nonnegative_index(
                header.get(offset_field), stage=stage, field=offset_field
            )
            count = _nonnegative_index(
                header.get(count_field), stage=stage, field=count_field
            )
            if offset + count > len(used) or any(used[offset : offset + count]):
                raise _error(stage, "immediate_report_invalid")
            for index in range(offset, offset + count):
                used[index] = True
            ranges.append((offset, count))
        contact_offset, contact_count = ranges[0]
        friction_offset, friction_count = ranges[1]
        group = groups.setdefault(
            pair_identity,
            {"headers": [], "contact_data": [], "friction_anchors": [], "fragments": []},
        )
        group["headers"].append(header)
        group["contact_data"].extend(
            copy.deepcopy(raw_contacts[index])
            for index in range(contact_offset, contact_offset + contact_count)
        )
        group["friction_anchors"].extend(
            copy.deepcopy(raw_friction[index])
            for index in range(friction_offset, friction_offset + friction_count)
        )
        group["fragments"].append(
            {
                "header": copy.deepcopy(header),
                "contact_data": [
                    copy.deepcopy(raw_contacts[index])
                    for index in range(contact_offset, contact_offset + contact_count)
                ],
                "friction_anchors": [
                    copy.deepcopy(raw_friction[index])
                    for index in range(friction_offset, friction_offset + friction_count)
                ],
            }
        )
    if not all(contact_used) or not all(friction_used):
        raise _error(stage, "immediate_report_invalid")
    if Counter(event_sequences) != Counter(
        _g2_sealed_compact_event_sequence(group["headers"])
        for group in groups.values()
    ):
        raise _error(stage, "immediate_report_invalid")
    return groups


def _g2_sealed_compact_event_sequence(headers: Sequence[Mapping[str, Any]]) -> str:
    events = []
    for header in headers:
        event = header["type"]
        if not events or events[-1] != event:
            events.append(event)
    return ",".join(events)


def _g2_sealed_validate_raw_physx_report(
    value: Any,
) -> tuple[dict[str, Any], set[tuple[str, str]], dict[tuple[str, str], dict[str, bool]]]:
    """Validate the complete immediate report before any derived contact view."""

    stage = "g2"
    if not isinstance(value, Mapping):
        raise _error(stage, "immediate_report_invalid")
    raw = copy.deepcopy(dict(value))
    if raw.get("authority") != "physx_immediate_full_contact_report_v1":
        raise _error(stage, "immediate_report_invalid")
    _nonnegative_index(raw.get("physics_index"), stage=stage, field="immediate_physics_index")
    for field in (
        "header_count",
        "contact_data_count",
        "friction_anchor_count",
        "occurrence_count",
        "current_pair_count",
        "bootstrap_pair_count",
        "immediate_read_index",
        "immediate_read_count",
    ):
        _nonnegative_index(raw.get(field), stage=stage, field=field)
    if raw.get("range_partition_valid") is not True or raw["immediate_read_count"] != raw["immediate_read_index"] + 1:
        raise _error(stage, "immediate_report_invalid")
    event_sequences = raw.get("event_sequences")
    occurrences = raw.get("occurrences")
    if (
        not isinstance(event_sequences, Sequence)
        or isinstance(event_sequences, (str, bytes, bytearray))
        or any(not isinstance(item, str) or not item for item in event_sequences)
        or not isinstance(occurrences, Sequence)
        or isinstance(occurrences, (str, bytes, bytearray))
        or raw["occurrence_count"] != len(occurrences)
    ):
        raise _error(stage, "immediate_report_invalid")
    header_groups = _g2_sealed_raw_header_groups(raw, event_sequences)

    current_raw = raw.get("current_pairs")
    if not isinstance(current_raw, Sequence) or isinstance(current_raw, (str, bytes, bytearray)):
        raise _error(stage, "immediate_report_invalid")
    current_identity = {
        _g2_sealed_raw_pair(pair, field="current_pair") for pair in current_raw
    }
    current_pairs = {_g2_sealed_path_pair(pair) for pair in current_identity}
    if len(current_identity) != len(current_raw) or len(current_pairs) != len(current_identity) or raw["current_pair_count"] != len(current_pairs):
        raise _error(stage, "immediate_report_invalid")

    occurrence_lifecycle: dict[tuple[str, str], dict[str, bool]] = {}
    occurrence_identity: set[tuple[tuple[str, int], tuple[str, int]]] = set()
    occurrence_identities: set[tuple[tuple[str, int], tuple[str, int]]] = set()
    bootstrap_count = 0
    for occurrence in occurrences:
        if not isinstance(occurrence, Mapping):
            raise _error(stage, "immediate_report_invalid")
        pair_identity = _g2_sealed_raw_pair(
            occurrence.get("canonical_pair"), field="occurrence_pair"
        )
        pair = _g2_sealed_path_pair(pair_identity)
        fragments = occurrence.get("fragments")
        group = header_groups.get(pair_identity)
        current = occurrence.get("current")
        transient = occurrence.get("transient")
        bootstrap = occurrence.get("bootstrap")
        if (
            pair_identity in occurrence_identity
            or pair in occurrence_lifecycle
            or not isinstance(fragments, Sequence)
            or isinstance(fragments, (str, bytes, bytearray))
            or not fragments
            or not isinstance(occurrence.get("event_sequence"), str)
            or not occurrence["event_sequence"]
            or type(current) is not bool
            or type(transient) is not bool
            or (not current and not transient)
            or (current and transient)
            or type(bootstrap) is not bool
            or group is None
            or occurrence.get("headers") != group["headers"]
            or occurrence.get("contact_data") != group["contact_data"]
            or occurrence.get("friction_anchors") != group["friction_anchors"]
            or list(fragments) != group["fragments"]
            or occurrence["event_sequence"]
            != _g2_sealed_compact_event_sequence(group["headers"])
        ):
            raise _error(stage, "immediate_report_invalid")
        event_types = tuple(
            _g2_sealed_compact_event_sequence(group["headers"]).split(",")
        )
        if (
            (current and not transient and event_types not in {("FOUND",), ("PERSIST",)})
            or (not current and transient and event_types not in {("FOUND", "LOST"), ("PERSIST", "LOST")})
            or (bootstrap and event_types != ("PERSIST",))
        ):
            raise _error(stage, "immediate_report_invalid")
        occurrence_identity.add(pair_identity)
        occurrence_identities.add(pair_identity)
        bootstrap_count += int(bootstrap)
        occurrence_lifecycle[pair] = {"current": current, "transient": transient}
    if any(
        pair_identity not in occurrence_identities
        and _g2_sealed_compact_event_sequence(group["headers"]) != "LOST"
        for pair_identity, group in header_groups.items()
    ) or raw["bootstrap_pair_count"] != bootstrap_count:
        raise _error(stage, "immediate_report_invalid")
    if {pair for pair, lifecycle in occurrence_lifecycle.items() if lifecycle["current"]} != current_pairs:
        raise _error(stage, "immediate_report_invalid")
    return raw, current_pairs, occurrence_lifecycle


def _g2_sealed_validate_roles(value: Mapping[str, Any]) -> dict[str, Any]:
    stage = "g2"
    source = _path_list(value.get("source_external_shell_paths"), stage=stage, field="source_external_shell_paths")
    support = _path_list(value.get("support_collider_paths"), stage=stage, field="support_collider_paths")
    wrappers = _path_list(value.get("source_wrapper_collider_paths"), stage=stage, field="source_wrapper_collider_paths")
    particles = _path_list(value.get("particle_collider_paths"), stage=stage, field="particle_collider_paths")
    hand = _path_list(value.get("hand_collider_paths"), stage=stage, field="hand_collider_paths")
    pads_raw = value.get("finger_pad_collider_paths")
    if not isinstance(pads_raw, Mapping) or set(pads_raw) != {"left", "right"}:
        raise _error(stage, "finger_pad_collider_paths_invalid")
    pads = {
        side: _path_list(pads_raw[side], stage=stage, field=f"{side}_finger_pad_collider_paths")
        for side in ("left", "right")
    }
    all_paths = [*source, *support, *wrappers, *particles, *hand, *pads["left"], *pads["right"]]
    if len(all_paths) != len(set(all_paths)):
        raise _error(stage, "collider_role_overlap_invalid")
    return {
        "source_external_shell_paths": sorted(source),
        "support_collider_paths": sorted(support),
        "source_wrapper_collider_paths": sorted(wrappers),
        "particle_collider_paths": sorted(particles),
        "hand_collider_paths": sorted(hand),
        "finger_pad_collider_paths": {side: sorted(paths) for side, paths in pads.items()},
    }


def _g2_sealed_validate_live_source_pose(value: Any) -> dict[str, list[float]]:
    if not isinstance(value, Mapping) or set(value) != {
        "position_world_m",
        "orientation_xyzw",
    }:
        raise _error("g2", "post_baseline_source_pose_invalid")
    position = _finite_vector(
        value["position_world_m"], shape=(3,), stage="g2", field="post_baseline_source_position"
    )
    orientation = _finite_vector(
        value["orientation_xyzw"], shape=(4,), stage="g2", field="post_baseline_source_orientation", unit=True
    )
    return {
        "position_world_m": position.tolist(),
        "orientation_xyzw": orientation.tolist(),
    }


def build_g2_baseline_contact_receipt(
    *,
    run_id: str,
    reset_epoch: int,
    fixture_identity_sha256: str,
    reset_raw_physx_report: Mapping[str, Any],
    post_baseline_source_pose: Mapping[str, Any],
    source_external_shell_paths: Sequence[str],
    support_collider_paths: Sequence[str],
    finger_pad_collider_paths: Mapping[str, Sequence[str]],
    hand_collider_paths: Sequence[str],
    source_wrapper_collider_paths: Sequence[str],
    particle_collider_paths: Sequence[str],
) -> dict[str, Any]:
    """Seal the reset-observed, non-robot source support contacts for G2."""

    if not isinstance(run_id, str) or not run_id:
        raise _error("g2", "run_id_invalid")
    epoch = _nonnegative_index(reset_epoch, stage="g2", field="reset_epoch")
    _sha256(fixture_identity_sha256, stage="g2", field="fixture_identity")
    roles = _g2_sealed_validate_roles(
        {
            "source_external_shell_paths": source_external_shell_paths,
            "support_collider_paths": support_collider_paths,
            "finger_pad_collider_paths": finger_pad_collider_paths,
            "hand_collider_paths": hand_collider_paths,
            "source_wrapper_collider_paths": source_wrapper_collider_paths,
            "particle_collider_paths": particle_collider_paths,
        }
    )
    live_pose = _g2_sealed_validate_live_source_pose(post_baseline_source_pose)
    raw, current_pairs, occurrences = _g2_sealed_validate_raw_physx_report(reset_raw_physx_report)
    source = set(roles["source_external_shell_paths"])
    support = set(roles["support_collider_paths"])
    if not current_pairs or any(not lifecycle["current"] for lifecycle in occurrences.values()):
        raise _error("g2", "baseline_pairs_invalid")
    for pair in current_pairs:
        if len(set(pair) & source) != 1 or len(set(pair) & support) != 1:
            raise _error("g2", "baseline_pairs_invalid")
    payload = {
        "authority": "real_pbd_g2_baseline_contact_receipt_v1",
        "schema_version": 1,
        "run_id": run_id,
        "reset_epoch": epoch,
        "fixture_identity_sha256": fixture_identity_sha256,
        "post_baseline_source_pose": live_pose,
        **roles,
        "reset_physics_step": raw["physics_index"],
        "reset_raw_physx_report": raw,
        "reset_raw_physx_report_sha256": canonical_json_sha256(raw),
        "baseline_pairs": [list(pair) for pair in sorted(current_pairs)],
    }
    return {**payload, "evidence_sha256": canonical_json_sha256(payload)}


def _g2_sealed_validate_baseline(value: Any) -> dict[str, Any]:
    checked = _hash_checked_mapping(
        value,
        stage="g2",
        authority="real_pbd_g2_baseline_contact_receipt_v1",
    )
    expected = {
        "authority", "schema_version", "run_id", "reset_epoch", "fixture_identity_sha256",
        "post_baseline_source_pose",
        "source_external_shell_paths", "support_collider_paths", "finger_pad_collider_paths",
        "hand_collider_paths", "source_wrapper_collider_paths", "particle_collider_paths",
        "reset_physics_step", "reset_raw_physx_report", "reset_raw_physx_report_sha256",
        "baseline_pairs", "evidence_sha256",
    }
    if set(checked) != expected or checked["schema_version"] != 1:
        raise _error("g2", "baseline_receipt_invalid")
    rebuilt = build_g2_baseline_contact_receipt(
        run_id=checked["run_id"],
        reset_epoch=checked["reset_epoch"],
        fixture_identity_sha256=checked["fixture_identity_sha256"],
        reset_raw_physx_report=checked["reset_raw_physx_report"],
        post_baseline_source_pose=checked["post_baseline_source_pose"],
        source_external_shell_paths=checked["source_external_shell_paths"],
        support_collider_paths=checked["support_collider_paths"],
        finger_pad_collider_paths=checked["finger_pad_collider_paths"],
        hand_collider_paths=checked["hand_collider_paths"],
        source_wrapper_collider_paths=checked["source_wrapper_collider_paths"],
        particle_collider_paths=checked["particle_collider_paths"],
    )
    if checked != rebuilt:
        raise _error("g2", "baseline_receipt_invalid")
    return checked


def _g2_sealed_validate_g0_decision(value: Any, certificate: Mapping[str, Any]) -> dict[str, Any]:
    checked = _hash_checked_mapping(
        value, stage="g2", authority="real_pbd_g0_clearance_decision_v1", hash_field="sha256"
    )
    if (
        checked.get("decision") != "G0_GO"
        or checked.get("certificate_sha256") != canonical_json_sha256(dict(certificate))
        or not isinstance(checked.get("selected_candidate_sha256"), str)
        or not isinstance(checked.get("fixture_identity"), Mapping)
    ):
        raise _error("g2", "g0_decision_invalid")
    _sha256(checked["selected_candidate_sha256"], stage="g2", field="selected_candidate")
    for field in ("usd_dependency_closure_sha256", "composed_collision_inventory_sha256"):
        _sha256(checked["fixture_identity"].get(field), stage="g2", field=field)
    return checked


def _g2_sealed_validate_trajectory(value: Any) -> dict[str, Any]:
    checked = _hash_checked_mapping(
        value, stage="g2", authority="real_pbd_g2_trajectory_spec_v1", hash_field="trajectory_sha256"
    )
    actions = checked.get("actions")
    if not isinstance(actions, Sequence) or isinstance(actions, (str, bytes, bytearray)):
        raise _error("g2", "trajectory_invalid")
    expectations = {}
    for action in actions:
        if not isinstance(action, Mapping):
            raise _error("g2", "trajectory_invalid")
        phase = action.get("phase")
        if phase not in _G2_PHASES or phase in expectations or action.get("semantic_action_kind") not in _G2_ACTION_KINDS[phase]:
            raise _error("g2", "trajectory_invalid")
        channel = action.get("channel")
        if channel not in {"arm", "finger"}:
            raise _error("g2", "trajectory_invalid")
        expectations[phase] = {
            "semantic_action_kind": action["semantic_action_kind"],
            "channel": channel,
            "target_token_sha256": _sha256(action.get("target_token_sha256"), stage="g2", field="target_token"),
        }
    if set(expectations) != _G2_PHASES or checked.get("lift_allowed") is not False or checked.get("pour_allowed") is not False:
        raise _error("g2", "trajectory_invalid")
    _sha256(checked.get("candidate_sha256"), stage="g2", field="trajectory_candidate")
    return {**checked, "action_expectations": dict(sorted(expectations.items()))}


def _g2_sealed_validate_bilateral_policy(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != {
        "required_consecutive_steps",
        "maximum_one_sided_steps",
    }:
        raise _error("g2", "bilateral_policy_invalid")
    required = _nonnegative_index(
        value["required_consecutive_steps"], stage="g2", field="required_consecutive_steps"
    )
    maximum_one_sided = _nonnegative_index(
        value["maximum_one_sided_steps"], stage="g2", field="maximum_one_sided_steps"
    )
    if required == 0:
        raise _error("g2", "bilateral_policy_invalid")
    return {
        "required_consecutive_steps": required,
        "maximum_one_sided_steps": maximum_one_sided,
    }


def build_g2_execution_context(
    *,
    run_id: str,
    reset_epoch: int,
    g0_certificate: Mapping[str, Any],
    g0_decision: Mapping[str, Any],
    trajectory: Mapping[str, Any],
    baseline_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind G0 geometry, the selected candidate, reset baseline, and actions."""

    if not isinstance(run_id, str) or not run_id:
        raise _error("g2", "run_id_invalid")
    epoch = _nonnegative_index(reset_epoch, stage="g2", field="reset_epoch")
    certificate = copy.deepcopy(dict(g0_certificate)) if isinstance(g0_certificate, Mapping) else None
    if certificate is None:
        raise _error("g2", "g0_certificate_invalid")
    evaluated = evaluate_g0_clearance_certificate(certificate)
    decision = _g2_sealed_validate_g0_decision(g0_decision, certificate)
    if decision != evaluated:
        raise _error("g2", "g0_decision_invalid")
    baseline = _g2_sealed_validate_baseline(baseline_receipt)
    derived_trajectory = _g2_sealed_validate_trajectory(trajectory)
    fixture, _ = _validate_g0_fixture(certificate.get("fixture"))
    raw_candidates = certificate.get("candidate_set", {}).get("candidates", [])
    selected_candidate = next(
        (
            candidate
            for candidate in raw_candidates
            if isinstance(candidate, Mapping)
            and canonical_json_sha256(dict(candidate))
            == decision["selected_candidate_sha256"]
        ),
        None,
    )
    if selected_candidate is None:
        raise _error("g2", "execution_context_binding_invalid")
    bilateral_policy = _g2_sealed_validate_bilateral_policy(
        selected_candidate.get("bilateral_policy")
    )
    expected_trajectory = build_g2_trajectory_spec(
        candidate=selected_candidate,
        live_source_pose=baseline["post_baseline_source_pose"],
    )
    if dict(trajectory) != expected_trajectory:
        raise _error("g2", "trajectory_binding_invalid")
    expected_fixture_identity = canonical_json_sha256(decision["fixture_identity"])
    if (
        baseline["run_id"] != run_id
        or baseline["reset_epoch"] != epoch
        or baseline["fixture_identity_sha256"] != expected_fixture_identity
        or derived_trajectory["candidate_sha256"] != decision["selected_candidate_sha256"]
        or derived_trajectory["source_pose_sha256"]
        != canonical_json_sha256(baseline["post_baseline_source_pose"])
        or fixture["source_external_shell_paths"] != baseline["source_external_shell_paths"]
        or fixture["support_collider_paths"] != baseline["support_collider_paths"]
        or fixture["source_internal_wrapper_paths"] != baseline["source_wrapper_collider_paths"]
        or baseline["particle_collider_paths"] != [fixture["particle_path"]]
        or fixture["hand_collider_paths"] != baseline["hand_collider_paths"]
        or fixture["finger_pad_collider_paths"] != baseline["finger_pad_collider_paths"]
    ):
        raise _error("g2", "execution_context_binding_invalid")
    payload = {
        "authority": "real_pbd_g2_execution_context_v1",
        "schema_version": 1,
        "run_id": run_id,
        "reset_epoch": epoch,
        "fixture_identity_sha256": expected_fixture_identity,
        "g0_certificate": certificate,
        "g0_decision": decision,
        "trajectory": copy.deepcopy(dict(trajectory)),
        "baseline_receipt": baseline,
        "selected_candidate_sha256": decision["selected_candidate_sha256"],
        "trajectory_sha256": derived_trajectory["trajectory_sha256"],
        "action_expectations": derived_trajectory["action_expectations"],
        "bilateral_policy": bilateral_policy,
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


def _g2_sealed_validate_context(value: Any) -> dict[str, Any]:
    checked = _hash_checked_mapping(
        value, stage="g2", authority="real_pbd_g2_execution_context_v1", hash_field="sha256"
    )
    expected = {
        "authority", "schema_version", "run_id", "reset_epoch", "fixture_identity_sha256",
        "g0_certificate", "g0_decision", "trajectory", "baseline_receipt",
        "selected_candidate_sha256", "trajectory_sha256", "action_expectations",
        "bilateral_policy", "sha256",
    }
    if set(checked) != expected or checked["schema_version"] != 1:
        raise _error("g2", "execution_context_invalid")
    rebuilt = build_g2_execution_context(
        run_id=checked["run_id"],
        reset_epoch=checked["reset_epoch"],
        g0_certificate=checked["g0_certificate"],
        g0_decision=checked["g0_decision"],
        trajectory=checked["trajectory"],
        baseline_receipt=checked["baseline_receipt"],
    )
    if checked != rebuilt:
        raise _error("g2", "execution_context_invalid")
    return checked


def build_g2_immediate_report_envelope(
    raw_physx_report: Mapping[str, Any],
    *,
    execution_context: Mapping[str, Any],
    phase: str,
    interval_index: int,
    substep_slot: int,
    substeps_per_interval: int,
) -> dict[str, Any]:
    """Seal a complete immediate PhysX report to one G2 action substep."""

    context = _g2_sealed_validate_context(execution_context)
    if phase not in _G2_PHASES:
        raise _error("g2", "phase_invalid")
    interval = _nonnegative_index(interval_index, stage="g2", field="interval_index")
    slot = _nonnegative_index(substep_slot, stage="g2", field="substep_slot")
    total = _nonnegative_index(substeps_per_interval, stage="g2", field="substeps_per_interval")
    if total == 0 or slot == 0 or slot > total:
        raise _error("g2", "substep_slot_invalid")
    raw, _, _ = _g2_sealed_validate_raw_physx_report(raw_physx_report)
    if raw["physics_index"] <= context["baseline_receipt"]["reset_physics_step"]:
        raise _error("g2", "immediate_report_prebaseline_invalid")
    payload = {
        "authority": "real_pbd_g2_immediate_report_envelope_v1",
        "schema_version": 1,
        "execution_context_sha256": context["sha256"],
        "run_id": context["run_id"],
        "reset_epoch": context["reset_epoch"],
        "physics_index": raw["physics_index"],
        "phase": phase,
        "interval_index": interval,
        "substep_slot": slot,
        "substeps_per_interval": total,
        "current_pairs": copy.deepcopy(raw["current_pairs"]),
        "occurrences": copy.deepcopy(raw["occurrences"]),
        "raw_physx_report": raw,
        "raw_physx_report_sha256": canonical_json_sha256(raw),
    }
    return {**payload, "evidence_sha256": canonical_json_sha256(payload)}


def _g2_sealed_validate_envelope(value: Any, *, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    checked = _hash_checked_mapping(
        value, stage="g2", authority="real_pbd_g2_immediate_report_envelope_v1"
    )
    expected = {
        "authority", "schema_version", "execution_context_sha256", "run_id", "reset_epoch",
        "physics_index", "phase", "interval_index", "substep_slot", "substeps_per_interval",
        "current_pairs", "occurrences", "raw_physx_report", "raw_physx_report_sha256", "evidence_sha256",
    }
    if set(checked) != expected or checked["schema_version"] != 1:
        raise _error("g2", "immediate_report_invalid")
    raw, _, _ = _g2_sealed_validate_raw_physx_report(checked["raw_physx_report"])
    if (
        checked["raw_physx_report_sha256"] != canonical_json_sha256(raw)
        or checked["physics_index"] != raw["physics_index"]
        or checked["current_pairs"] != raw["current_pairs"]
        or checked["occurrences"] != raw["occurrences"]
        or checked["phase"] not in _G2_PHASES
    ):
        raise _error("g2", "immediate_report_invalid")
    _nonnegative_index(checked["interval_index"], stage="g2", field="interval_index")
    slot = _nonnegative_index(checked["substep_slot"], stage="g2", field="substep_slot")
    total = _nonnegative_index(checked["substeps_per_interval"], stage="g2", field="substeps_per_interval")
    if total == 0 or slot == 0 or slot > total:
        raise _error("g2", "immediate_report_invalid")
    if context is not None and (
        checked["execution_context_sha256"] != context["sha256"]
        or checked["run_id"] != context["run_id"]
        or checked["reset_epoch"] != context["reset_epoch"]
    ):
        raise _error("g2", "immediate_report_context_invalid")
    if context is not None and checked["physics_index"] <= context["baseline_receipt"][
        "reset_physics_step"
    ]:
        raise _error("g2", "immediate_report_prebaseline_invalid")
    return checked


def build_g2_classification_receipt(
    *, immediate_report_envelope: Mapping[str, Any], classification: Mapping[str, Any]
) -> dict[str, Any]:
    """Bind classifier output to every immediate-report occurrence, including transients."""

    envelope = _g2_sealed_validate_envelope(immediate_report_envelope)
    raw, current_pairs, occurrences = _g2_sealed_validate_raw_physx_report(envelope["raw_physx_report"])
    classified = _hash_checked_mapping(
        classification, stage="g2", authority="controlled_contact_complete_immediate_report_v1"
    )
    if classified.get("physics_step") != raw["physics_index"] or classified.get("phase") != envelope["phase"]:
        raise _error("g2", "classification_identity_invalid")
    records = classified.get("records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)):
        raise _error("g2", "classification_coverage_invalid")
    normalized_records = []
    covered: set[tuple[str, str]] = set()
    for raw_record in records:
        if not isinstance(raw_record, Mapping) or not isinstance(raw_record.get("pair"), Mapping):
            raise _error("g2", "classification_coverage_invalid")
        record = copy.deepcopy(dict(raw_record))
        pair = _g2_sealed_pair(record["pair"].get("collider_paths"), field="classification_pair")
        if pair in covered or pair not in occurrences:
            raise _error("g2", "classification_coverage_invalid")
        lifecycle = occurrences[pair]
        has_current = "current" in record
        has_transient = "transient" in record
        if has_current != has_transient:
            raise _error("g2", "classification_lifecycle_invalid")
        if not has_current:
            record["current"] = lifecycle["current"]
            record["transient"] = lifecycle["transient"]
        elif record["current"] is not lifecycle["current"] or record["transient"] is not lifecycle["transient"]:
            raise _error("g2", "classification_lifecycle_invalid")
        covered.add(pair)
        normalized_records.append(record)
    if covered != set(occurrences):
        raise _error("g2", "classification_coverage_invalid")
    normalized = {**classified, "records": normalized_records}
    records_by_pair, terminal, transient_intended = _classification_records(
        normalized, raw_pairs=current_pairs
    )
    payload = {
        "authority": "real_pbd_g2_classification_receipt_v1",
        "schema_version": 1,
        "execution_context_sha256": envelope["execution_context_sha256"],
        "immediate_report_evidence_sha256": envelope["evidence_sha256"],
        "physics_step": raw["physics_index"],
        "phase": envelope["phase"],
        "classifier_evidence_sha256": classified["evidence_sha256"],
        "raw_classification": classified,
        "records": normalized_records,
        "class_counts": normalized["class_counts"],
        "terminal_kind": terminal,
        "source_motion_authority_valid": normalized["source_motion_authority_valid"],
        "transient_intended_contact": transient_intended,
    }
    return {**payload, "evidence_sha256": canonical_json_sha256(payload)}


def _g2_sealed_validate_classification(
    value: Any, *, envelope: Mapping[str, Any], context: Mapping[str, Any]
) -> dict[str, Any]:
    checked = _hash_checked_mapping(value, stage="g2", authority="real_pbd_g2_classification_receipt_v1")
    expected = {
        "authority", "schema_version", "execution_context_sha256", "immediate_report_evidence_sha256",
        "physics_step", "phase", "classifier_evidence_sha256", "raw_classification", "records",
        "class_counts", "terminal_kind", "source_motion_authority_valid", "transient_intended_contact", "evidence_sha256",
    }
    if set(checked) != expected or checked["schema_version"] != 1:
        raise _error("g2", "classification_receipt_invalid")
    if checked["execution_context_sha256"] != context["sha256"] or checked["immediate_report_evidence_sha256"] != envelope["evidence_sha256"]:
        raise _error("g2", "classification_receipt_binding_invalid")
    rebuilt = build_g2_classification_receipt(
        immediate_report_envelope=envelope, classification=checked["raw_classification"]
    )
    if checked != rebuilt:
        raise _error("g2", "classification_receipt_invalid")
    return checked


def build_g2_sensor_pair_receipt(
    *, immediate_report_envelope: Mapping[str, Any], normalized_sensor_contacts: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Seal same-step sensor pairs to the exact immediate-report envelope."""

    envelope = _g2_sealed_validate_envelope(immediate_report_envelope)
    if not isinstance(normalized_sensor_contacts, Sequence) or isinstance(normalized_sensor_contacts, (str, bytes, bytearray)):
        raise _error("g2", "sensor_receipt_invalid")
    contacts = []
    pairs: set[tuple[str, str]] = set()
    for contact in normalized_sensor_contacts:
        if not isinstance(contact, Mapping) or contact.get("physics_step") != envelope["physics_index"]:
            raise _error("g2", "sensor_receipt_invalid")
        pair = _g2_sealed_pair(
            [contact.get("collider0_path"), contact.get("collider1_path")], field="sensor_pair"
        )
        pairs.add(pair)
        contacts.append(copy.deepcopy(dict(contact)))
    payload = {
        "authority": "real_pbd_g2_sensor_pair_receipt_v1",
        "schema_version": 1,
        "execution_context_sha256": envelope["execution_context_sha256"],
        "immediate_report_evidence_sha256": envelope["evidence_sha256"],
        "physics_step": envelope["physics_index"],
        "pairs": [list(pair) for pair in sorted(pairs)],
        "normalized_sensor_contacts": contacts,
    }
    return {**payload, "evidence_sha256": canonical_json_sha256(payload)}


def _g2_sealed_validate_sensor(
    value: Any, *, envelope: Mapping[str, Any], context: Mapping[str, Any]
) -> dict[str, Any]:
    checked = _hash_checked_mapping(value, stage="g2", authority="real_pbd_g2_sensor_pair_receipt_v1")
    expected = {
        "authority", "schema_version", "execution_context_sha256", "immediate_report_evidence_sha256",
        "physics_step", "pairs", "normalized_sensor_contacts", "evidence_sha256",
    }
    if set(checked) != expected or checked["schema_version"] != 1:
        raise _error("g2", "sensor_receipt_invalid")
    if checked["execution_context_sha256"] != context["sha256"] or checked["immediate_report_evidence_sha256"] != envelope["evidence_sha256"]:
        raise _error("g2", "sensor_receipt_binding_invalid")
    rebuilt = build_g2_sensor_pair_receipt(
        immediate_report_envelope=envelope,
        normalized_sensor_contacts=checked["normalized_sensor_contacts"],
    )
    if checked != rebuilt:
        raise _error("g2", "sensor_receipt_invalid")
    return checked


def _g2_sealed_validate_source_state_payload(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise _error("g2", "source_state_receipt_invalid")
    for boundary in ("pre", "post"):
        state = value.get(boundary)
        if not isinstance(state, Mapping):
            raise _error("g2", "source_state_receipt_invalid")
        _finite_vector(state.get("com_position_m"), shape=(3,), stage="g2", field="source_com")
        _finite_vector(state.get("orientation_wxyz"), shape=(4,), stage="g2", field="source_orientation", unit=True)
        _finite_vector(state.get("linear_velocity_m_s"), shape=(3,), stage="g2", field="source_linear_velocity")
        _finite_vector(state.get("angular_velocity_rad_s"), shape=(3,), stage="g2", field="source_angular_velocity")


def build_g2_source_state_receipt(
    *, execution_context: Mapping[str, Any], physics_step: int, interval_index: int,
    substep_slot: int, phase: str, pre: Mapping[str, Any], post: Mapping[str, Any]
) -> dict[str, Any]:
    context = _g2_sealed_validate_context(execution_context)
    step = _nonnegative_index(physics_step, stage="g2", field="physics_step")
    interval = _nonnegative_index(interval_index, stage="g2", field="interval_index")
    slot = _nonnegative_index(substep_slot, stage="g2", field="substep_slot")
    if phase not in _G2_PHASES:
        raise _error("g2", "phase_invalid")
    payload = {
        "authority": "real_pbd_g2_source_state_receipt_v1",
        "schema_version": 1,
        "execution_context_sha256": context["sha256"],
        "physics_step": step,
        "interval_index": interval,
        "substep_slot": slot,
        "phase": phase,
        "source_actor_path": context["g0_certificate"]["fixture"]["source_actor_path"],
        "pre": copy.deepcopy(dict(pre)),
        "post": copy.deepcopy(dict(post)),
    }
    _g2_sealed_validate_source_state_payload(payload)
    return {**payload, "evidence_sha256": canonical_json_sha256(payload)}


def _g2_sealed_validate_source_state(
    value: Any, *, envelope: Mapping[str, Any], context: Mapping[str, Any]
) -> dict[str, Any]:
    checked = _hash_checked_mapping(value, stage="g2", authority="real_pbd_g2_source_state_receipt_v1")
    expected = {
        "authority", "schema_version", "execution_context_sha256", "physics_step", "interval_index",
        "substep_slot", "phase", "source_actor_path", "pre", "post", "evidence_sha256",
    }
    if set(checked) != expected or checked["schema_version"] != 1:
        raise _error("g2", "source_state_receipt_invalid")
    if (
        checked["execution_context_sha256"] != context["sha256"]
        or checked["physics_step"] != envelope["physics_index"]
        or checked["interval_index"] != envelope["interval_index"]
        or checked["substep_slot"] != envelope["substep_slot"]
        or checked["phase"] != envelope["phase"]
        or checked["source_actor_path"]
        != context["g0_certificate"]["fixture"]["source_actor_path"]
    ):
        raise _error("g2", "source_state_receipt_binding_invalid")
    _g2_sealed_validate_source_state_payload(checked)
    return checked


def _g2_sealed_validate_applied_action(
    value: Any, *, context: Mapping[str, Any], envelope: Mapping[str, Any]
) -> dict[str, Any]:
    checked = _hash_checked_mapping(
        value, stage="g2", authority="controlled_action_applied_receipt_v1", hash_field="sha256"
    )
    phase = envelope["phase"]
    expected = context["action_expectations"].get(phase)
    if (
        expected is None
        or checked.get("phase") != phase
        or checked.get("controller_phase") != phase
        or checked.get("interval_index") != envelope["interval_index"]
        or checked.get("semantic_action_kind") != expected["semantic_action_kind"]
        or checked.get("channel") != expected["channel"]
        or checked.get("target_token_sha256") != expected["target_token_sha256"]
        or checked.get("applied") is not True
        or checked.get("normal_api_return") is not True
        or checked.get("physics_steps_before_receipt") != 0
    ):
        raise _error("g2", "action_receipt_invalid")
    target_token = checked.get("target_token")
    target_payload = copy.deepcopy(dict(target_token)) if isinstance(target_token, Mapping) else None
    target_digest = target_payload.pop("sha256", None) if target_payload is not None else None
    if (
        target_payload is None
        or target_digest != expected["target_token_sha256"]
        or canonical_json_sha256(target_payload) != target_digest
        or any(
            isinstance(checked.get(field), bool)
            or not isinstance(checked.get(field), (int, np.integer))
            or int(checked[field]) < 0
            for field in ("control_index", "action_index", "apply_index")
        )
        or checked["action_index"] != checked["apply_index"]
    ):
        raise _error("g2", "action_receipt_invalid")
    _sha256(checked.get("proposal_sha256"), stage="g2", field="action_proposal")
    _sha256(checked.get("commit_sha256"), stage="g2", field="action_commit")
    _sha256(checked.get("action_sha256"), stage="g2", field="action")
    return checked


def build_g2_applied_action_receipt(
    *,
    execution_context: Mapping[str, Any],
    immediate_report_envelope: Mapping[str, Any],
    applied_action_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind one loop-owned applied action to its resulting G2 readback step."""

    context = _g2_sealed_validate_context(execution_context)
    envelope = _g2_sealed_validate_envelope(immediate_report_envelope, context=context)
    applied = _g2_sealed_validate_applied_action(
        applied_action_receipt, context=context, envelope=envelope
    )
    payload = {
        "authority": "real_pbd_g2_applied_action_receipt_v1",
        "schema_version": 1,
        "execution_context_sha256": context["sha256"],
        "immediate_report_evidence_sha256": envelope["evidence_sha256"],
        "physics_step": envelope["physics_index"],
        "phase": envelope["phase"],
        "interval_index": envelope["interval_index"],
        "substep_slot": envelope["substep_slot"],
        "applied_action_receipt": applied,
        "applied_action_receipt_sha256": applied["sha256"],
    }
    return {**payload, "evidence_sha256": canonical_json_sha256(payload)}


def _g2_sealed_validate_action(
    value: Any, *, context: Mapping[str, Any], envelope: Mapping[str, Any]
) -> dict[str, Any]:
    checked = _hash_checked_mapping(
        value, stage="g2", authority="real_pbd_g2_applied_action_receipt_v1"
    )
    expected = {
        "authority", "schema_version", "execution_context_sha256",
        "immediate_report_evidence_sha256", "physics_step", "phase", "interval_index",
        "substep_slot", "applied_action_receipt", "applied_action_receipt_sha256",
        "evidence_sha256",
    }
    if set(checked) != expected or checked["schema_version"] != 1:
        raise _error("g2", "action_receipt_invalid")
    if (
        checked["execution_context_sha256"] != context["sha256"]
        or checked["immediate_report_evidence_sha256"] != envelope["evidence_sha256"]
        or checked["physics_step"] != envelope["physics_index"]
        or checked["phase"] != envelope["phase"]
        or checked["interval_index"] != envelope["interval_index"]
        or checked["substep_slot"] != envelope["substep_slot"]
    ):
        raise _error("g2", "action_receipt_binding_invalid")
    applied = _g2_sealed_validate_applied_action(
        checked["applied_action_receipt"], context=context, envelope=envelope
    )
    if checked["applied_action_receipt_sha256"] != applied["sha256"]:
        raise _error("g2", "action_receipt_invalid")
    return checked


def evaluate_g2_substep(
    *,
    execution_context: Mapping[str, Any],
    immediate_report_envelope: Mapping[str, Any],
    classification_receipt: Mapping[str, Any],
    sensor_receipt: Mapping[str, Any],
    source_state_receipt: Mapping[str, Any],
    action_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Fail closed unless all G2 inputs prove one identical launch substep."""

    context = _g2_sealed_validate_context(execution_context)
    envelope = _g2_sealed_validate_envelope(immediate_report_envelope, context=context)
    classification = _g2_sealed_validate_classification(
        classification_receipt, envelope=envelope, context=context
    )
    sensors = _g2_sealed_validate_sensor(sensor_receipt, envelope=envelope, context=context)
    source_state = _g2_sealed_validate_source_state(
        source_state_receipt, envelope=envelope, context=context
    )
    action = _g2_sealed_validate_action(
        action_receipt, context=context, envelope=envelope
    )
    _, current_pairs, occurrences = _g2_sealed_validate_raw_physx_report(envelope["raw_physx_report"])
    normalized = {
        "records": classification["records"],
        "class_counts": classification["class_counts"],
        "terminal_kind": classification["terminal_kind"],
        "source_motion_authority_valid": classification["source_motion_authority_valid"],
    }
    records, classified_terminal, transient_intended = _classification_records(
        normalized, raw_pairs=current_pairs
    )
    baseline = _g2_sealed_validate_baseline(context["baseline_receipt"])
    baseline_pairs = {_g2_sealed_pair(pair, field="baseline_pair") for pair in baseline["baseline_pairs"]}
    roles = _g2_sealed_validate_roles(baseline)
    source = set(roles["source_external_shell_paths"])
    pads = roles["finger_pad_collider_paths"]
    intended = {
        _g2_sealed_pair((pad, shell), field="intended_pair"): side
        for side, pad_paths in pads.items()
        for pad in pad_paths
        for shell in source
    }
    wrappers_particles = set(roles["source_wrapper_collider_paths"]) | set(roles["particle_collider_paths"])
    all_pads = set(pads["left"]) | set(pads["right"])
    protocol_failures: set[str] = set()
    physical_failures: set[str] = set()
    if classified_terminal == "PROTOCOL_FAILURE":
        protocol_failures.add("classification_protocol_terminal")
    elif classified_terminal in {"PHYSICAL_CONTACT_FAILURE", "PHYSICAL_MOTION_FAILURE"}:
        physical_failures.add("classification_physical_terminal")
    if transient_intended:
        physical_failures.add("transient_intended_contact")
    for pair, lifecycle in occurrences.items():
        if set(pair) & wrappers_particles:
            physical_failures.add("wrapper_or_particle_contact")
        if pair in baseline_pairs:
            if not lifecycle["current"]:
                physical_failures.add("baseline_contact_changed")
        elif pair in intended:
            if lifecycle["transient"]:
                physical_failures.add("transient_intended_contact")
        else:
            # A non-current FOUND/LOST contact is still a real collision breach;
            # it must not disappear merely because it was gone at readback.
            physical_failures.add("unexpected_observed_pair")
    active_background: set[tuple[str, str]] = set()
    active_sides: set[str] = set()
    for pair in current_pairs:
        record = records.get(pair)
        if record is None or record["current"] is not True:
            protocol_failures.add("immediate_pair_classification_gap")
            continue
        if pair in baseline_pairs:
            active_background.add(pair)
            if record["class"] != "BACKGROUND":
                protocol_failures.add("baseline_classification_mismatch")
            continue
        side = intended.get(pair)
        if side is None:
            physical_failures.add("unexpected_current_pair")
            continue
        active_sides.add(side)
        expected_class = (
            "INTENDED_PRECONTACT"
            if envelope["phase"] in _G2_PRECONTACT_PHASES
            else "INTENDED_CLOSE_CONTACT"
            if envelope["phase"] in _G2_CLOSE_PHASES
            else None
        )
        if expected_class is None:
            physical_failures.add("contact_outside_contact_phase")
        elif record["class"] != expected_class or record["side"] != side:
            physical_failures.add("intended_contact_classification_mismatch")
    if active_background != baseline_pairs:
        physical_failures.add("baseline_contact_changed")
    sensor_pairs = {_g2_sealed_pair(pair, field="sensor_pair") for pair in sensors["pairs"]}
    expected_sensor_pairs = {pair for pair in current_pairs if set(pair) & all_pads}
    if sensor_pairs != expected_sensor_pairs:
        protocol_failures.add("sensor_immediate_disagreement")
    terminal_kind = (
        "PROTOCOL_FAILURE" if protocol_failures else "PHYSICAL_CONTACT_FAILURE" if physical_failures else None
    )
    payload = {
        "authority": "real_pbd_g2_substep_decision_v1",
        "execution_context_sha256": context["sha256"],
        "physics_step": envelope["physics_index"],
        "interval_index": envelope["interval_index"],
        "substep_slot": envelope["substep_slot"],
        "substeps_per_interval": envelope["substeps_per_interval"],
        "phase": envelope["phase"],
        "raw_immediate_report_sha256": envelope["evidence_sha256"],
        "classification_evidence_sha256": classification["evidence_sha256"],
        "sensor_receipt_sha256": sensors["evidence_sha256"],
        "baseline_receipt_sha256": baseline["evidence_sha256"],
        "action_receipt_sha256": action["evidence_sha256"],
        "source_state_receipt_sha256": source_state["evidence_sha256"],
        "current_intended_sides": sorted(active_sides),
        "terminal_kind": terminal_kind,
        "protocol_failures": sorted(protocol_failures),
        "physical_failures": sorted(physical_failures),
        "remaining_substeps_allowed": terminal_kind is None,
        "next_action_allowed": terminal_kind is None,
        "lift_allowed": False,
        "pour_allowed": False,
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


class G2BilateralCertificate:
    """Accumulate close-only bilateral contact without granting a lift command."""

    def __init__(
        self,
        *,
        execution_context: Mapping[str, Any],
    ) -> None:
        context = _g2_sealed_validate_context(execution_context)
        policy = _g2_sealed_validate_bilateral_policy(context["bilateral_policy"])
        self.required_consecutive_steps = policy["required_consecutive_steps"]
        self.maximum_one_sided_steps = policy["maximum_one_sided_steps"]
        self._execution_context_sha256 = context["sha256"]
        self._last_physics_step: int | None = None
        self._consecutive_bilateral_steps = 0
        self._one_sided_steps = 0
        self._terminal_kind: str | None = None

    def observe(self, substep: Mapping[str, Any]) -> dict[str, Any]:
        stage = "g2"
        checked = _hash_checked_mapping(
            substep,
            stage=stage,
            authority="real_pbd_g2_substep_decision_v1",
            hash_field="sha256",
        )
        if checked.get("execution_context_sha256") != self._execution_context_sha256:
            raise _error(stage, "bilateral_certificate_context_invalid")
        expected_fields = {
            "authority", "execution_context_sha256", "physics_step", "interval_index",
            "substep_slot", "substeps_per_interval", "phase", "raw_immediate_report_sha256",
            "classification_evidence_sha256", "sensor_receipt_sha256", "baseline_receipt_sha256",
            "action_receipt_sha256", "source_state_receipt_sha256", "current_intended_sides",
            "terminal_kind", "protocol_failures", "physical_failures",
            "remaining_substeps_allowed", "next_action_allowed", "lift_allowed", "pour_allowed",
            "sha256",
        }
        if (
            set(checked) != expected_fields
            or checked.get("phase") not in _G2_PHASES
            or checked.get("lift_allowed") is not False
            or checked.get("pour_allowed") is not False
            or type(checked.get("remaining_substeps_allowed")) is not bool
            or type(checked.get("next_action_allowed")) is not bool
        ):
            raise _error(stage, "bilateral_certificate_substep_invalid")
        physics_step = _nonnegative_index(
            checked.get("physics_step"), stage=stage, field="certificate_physics_step"
        )
        if (
            self._last_physics_step is not None
            and physics_step != self._last_physics_step + 1
        ):
            raise _error(stage, "bilateral_certificate_physics_step_invalid")
        self._last_physics_step = physics_step
        terminal = checked.get("terminal_kind")
        if terminal not in {
            None,
            "PROTOCOL_FAILURE",
            "PHYSICAL_CONTACT_FAILURE",
            "PHYSICAL_MOTION_FAILURE",
        }:
            raise _error(stage, "bilateral_certificate_terminal_invalid")
        if self._terminal_kind is not None:
            terminal = "PROTOCOL_FAILURE"
        elif terminal is not None:
            self._terminal_kind = terminal
        elif checked.get("phase") in _G2_CLOSE_PHASES:
            sides = checked.get("current_intended_sides")
            if not isinstance(sides, Sequence) or isinstance(
                sides, (str, bytes, bytearray)
            ) or any(side not in {"left", "right"} for side in sides):
                raise _error(stage, "bilateral_certificate_sides_invalid")
            side_set = set(sides)
            if side_set == {"left", "right"}:
                self._consecutive_bilateral_steps += 1
                self._one_sided_steps = 0
            elif len(side_set) == 1:
                self._consecutive_bilateral_steps = 0
                self._one_sided_steps += 1
                if self._one_sided_steps > self.maximum_one_sided_steps:
                    terminal = "PHYSICAL_CONTACT_FAILURE"
                    self._terminal_kind = terminal
            else:
                self._consecutive_bilateral_steps = 0
                self._one_sided_steps = 0

        certified = bool(
            terminal is None
            and self._consecutive_bilateral_steps >= self.required_consecutive_steps
        )
        payload = {
            "authority": "real_pbd_g2_bilateral_certificate_v1",
            "execution_context_sha256": self._execution_context_sha256,
            "physics_step": physics_step,
            "required_consecutive_steps": self.required_consecutive_steps,
            "consecutive_bilateral_steps": self._consecutive_bilateral_steps,
            "one_sided_steps": self._one_sided_steps,
            "terminal_kind": terminal,
            "certified": certified,
            "substep_sha256": checked["sha256"],
            "lift_allowed": False,
            "pour_allowed": False,
        }
        return {**payload, "sha256": canonical_json_sha256(payload)}


def _rotate_xyzw(quaternion: np.ndarray, vector: np.ndarray) -> np.ndarray:
    imaginary = quaternion[:3]
    return vector + 2.0 * np.cross(
        imaginary,
        np.cross(imaginary, vector) + quaternion[3] * vector,
    )


def build_g2_trajectory_spec(
    *, candidate: Mapping[str, Any], live_source_pose: Mapping[str, Any]
) -> dict[str, Any]:
    """Derive a new close-only target sequence from a live PBD source pose."""

    stage = "g2"
    if not isinstance(candidate, Mapping):
        raise _error(stage, "candidate_provenance_invalid")
    raw_candidate = copy.deepcopy(dict(candidate))
    forbidden_keys = {
        "source_transition_index",
        "frozen_v6_action_sha256",
        "frozen_action_sha256",
        "source_trace_action_hash",
        "frozen_trace",
    }
    if forbidden_keys & set(raw_candidate):
        raise _error(stage, "candidate_provenance_invalid")
    if raw_candidate.get("authority") != "real_pbd_g0_candidate_v1":
        raise _error(stage, "candidate_provenance_invalid")
    identifier = raw_candidate.get("id")
    if not isinstance(identifier, str) or not identifier:
        raise _error(stage, "candidate_provenance_invalid")
    if not isinstance(live_source_pose, Mapping):
        raise _error(stage, "live_source_pose_invalid")
    source_position = _finite_vector(
        live_source_pose.get("position_world_m"),
        shape=(3,),
        stage=stage,
        field="live_source_position",
    )
    source_orientation = _finite_vector(
        live_source_pose.get("orientation_xyzw"),
        shape=(4,),
        stage=stage,
        field="live_source_orientation",
        unit=True,
    )
    offset = _finite_vector(
        raw_candidate.get("source_frame_grasp_offset_m"),
        shape=(3,),
        stage=stage,
        field="source_frame_grasp_offset",
    )
    approach = _finite_vector(
        raw_candidate.get("approach_direction_world"),
        shape=(3,),
        stage=stage,
        field="approach_direction",
        unit=True,
    )
    if not np.allclose(approach, [0.0, 0.0, -1.0], rtol=0.0, atol=1.0e-12):
        raise _error(stage, "candidate_not_top_down")
    pregrasp_distance = _finite_number(
        raw_candidate.get("pregrasp_distance_m"),
        stage=stage,
        field="pregrasp_distance",
        positive=True,
    )
    insert_distance = _finite_number(
        raw_candidate.get("insert_distance_m"),
        stage=stage,
        field="insert_distance",
        positive=True,
    )
    if insert_distance > pregrasp_distance:
        raise _error(stage, "insert_distance_invalid")
    orientation = _finite_vector(
        raw_candidate.get("tool_orientation_wxyz"),
        shape=(4,),
        stage=stage,
        field="tool_orientation",
        unit=True,
    )
    control_offset = _finite_vector(
        raw_candidate.get("control_target_offset_world_m"),
        shape=(3,),
        stage=stage,
        field="control_target_offset",
    )
    raw_indices = raw_candidate.get("finger_joint_indices")
    if (
        not isinstance(raw_indices, Sequence)
        or isinstance(raw_indices, (str, bytes, bytearray))
        or len(raw_indices) != 2
        or len(set(raw_indices)) != 2
        or any(type(index) is not int or index < 0 for index in raw_indices)
    ):
        raise _error(stage, "finger_joint_indices_invalid")
    close_endpoint = _finite_number(
        raw_candidate.get("close_endpoint_m"),
        stage=stage,
        field="close_endpoint",
        positive=True,
    )
    if close_endpoint > 0.04:
        raise _error(stage, "close_endpoint_invalid")
    _finite_number(
        raw_candidate.get("close_speed_m_s"),
        stage=stage,
        field="close_speed",
        positive=True,
    )

    grasp = source_position + _rotate_xyzw(source_orientation, offset)
    pregrasp = grasp - approach * pregrasp_distance
    align = grasp - approach * insert_distance
    arm_targets = {
        "PREGRASP": pregrasp,
        "ALIGN": align,
        "INSERT": grasp,
        "SETTLE": grasp,
        "PRECONTACT_SETTLE": grasp,
    }
    actions = []
    semantic_actions = {
        "PREGRASP": "ARM_PREGRASP",
        "ALIGN": "ARM_ALIGN",
        "INSERT": "ARM_INSERT",
        "SETTLE": "ARM_SETTLE",
        "PRECONTACT_SETTLE": "ARM_PRECONTACT_SETTLE",
    }
    for phase, target in arm_targets.items():
        control_target = target + control_offset
        token = build_arm_target_token(
            tool_position_stage_units=target,
            tool_orientation_wxyz=orientation,
            control_position_stage_units=control_target,
            control_orientation_wxyz=orientation,
            tool_frame="tool_center",
            control_frame="right_gripper",
            stage_units_m=1.0,
        )
        actions.append(
            {
                "phase": phase,
                "semantic_action_kind": semantic_actions[phase],
                "channel": "arm",
                "target_token": token,
                "target_token_sha256": token["sha256"],
            }
        )
    finger_token = build_finger_target_token(
        joint_indices=raw_indices,
        joint_targets=(close_endpoint, close_endpoint),
    )
    for phase, semantic_action_kind in (
        ("CLOSE", "GRIPPER_CLOSE"),
        ("CONTACT_SETTLE", "GRIPPER_CONTACT_SETTLE"),
    ):
        actions.append(
            {
                "phase": phase,
                "semantic_action_kind": semantic_action_kind,
                "channel": "finger",
                "target_token": copy.deepcopy(finger_token),
                "target_token_sha256": finger_token["sha256"],
            }
        )
    source_payload = {
        "position_world_m": source_position.tolist(),
        "orientation_xyzw": source_orientation.tolist(),
    }
    payload = {
        "authority": "real_pbd_g2_trajectory_spec_v1",
        "candidate_id": identifier,
        "candidate_sha256": canonical_json_sha256(raw_candidate),
        "source_pose_sha256": canonical_json_sha256(source_payload),
        "grasp_position_world_m": grasp.tolist(),
        "actions": actions,
        "new_action_trace_required": True,
        "frozen_trace_input_allowed": False,
        "lift_allowed": False,
        "pour_allowed": False,
    }
    return {**payload, "trajectory_sha256": canonical_json_sha256(payload)}


def build_source_stage_authoring_snapshot(
    *,
    source_actor_path: str,
    source_prim_type: str,
    source_reference_sha256: str,
    source_transform_authored_sha256: str,
    source_velocity_authored_sha256: str,
    source_kinematic_enabled: bool,
    source_collision_filter_sha256: str,
    source_collision_api_sha256: str,
    source_attachment_constraint_paths: Sequence[str],
    source_collider_inventory_sha256: str,
) -> dict[str, Any]:
    """Seal authored source state separately from its permitted runtime motion."""

    stage = "source_stage"
    _path(source_actor_path, stage=stage, field="source_actor_path")
    if not isinstance(source_prim_type, str) or not source_prim_type:
        raise _error(stage, "source_prim_type_invalid")
    for field, value in (
        ("source_reference_sha256", source_reference_sha256),
        ("source_transform_authored_sha256", source_transform_authored_sha256),
        ("source_velocity_authored_sha256", source_velocity_authored_sha256),
        ("source_collision_filter_sha256", source_collision_filter_sha256),
        ("source_collision_api_sha256", source_collision_api_sha256),
        ("source_collider_inventory_sha256", source_collider_inventory_sha256),
    ):
        _sha256(value, stage=stage, field=field)
    if type(source_kinematic_enabled) is not bool:
        raise _error(stage, "source_kinematic_enabled_invalid")
    attachment_paths = _path_list(
        source_attachment_constraint_paths,
        stage=stage,
        field="source_attachment_constraint_paths",
        allow_empty=True,
    )
    payload = {
        "authority": "real_pbd_source_stage_authoring_snapshot_v1",
        "source_actor_path": source_actor_path,
        "source_prim_type": source_prim_type,
        "source_reference_sha256": source_reference_sha256,
        "source_transform_authored_sha256": source_transform_authored_sha256,
        "source_velocity_authored_sha256": source_velocity_authored_sha256,
        "source_kinematic_enabled": source_kinematic_enabled,
        "source_collision_filter_sha256": source_collision_filter_sha256,
        "source_collision_api_sha256": source_collision_api_sha256,
        "source_attachment_constraint_paths": sorted(attachment_paths),
        "source_collider_inventory_sha256": source_collider_inventory_sha256,
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


def _validate_source_stage_authoring_snapshot(value: Any) -> dict[str, Any]:
    stage = "source_stage"
    snapshot = _hash_checked_mapping(
        value,
        stage=stage,
        authority="real_pbd_source_stage_authoring_snapshot_v1",
        hash_field="sha256",
    )
    expected_fields = {
        "authority",
        "source_actor_path",
        "source_prim_type",
        "source_reference_sha256",
        "source_transform_authored_sha256",
        "source_velocity_authored_sha256",
        "source_kinematic_enabled",
        "source_collision_filter_sha256",
        "source_collision_api_sha256",
        "source_attachment_constraint_paths",
        "source_collider_inventory_sha256",
        "sha256",
    }
    if set(snapshot) != expected_fields:
        raise _error(stage, "snapshot_fields_invalid")
    return build_source_stage_authoring_snapshot(
        source_actor_path=snapshot["source_actor_path"],
        source_prim_type=snapshot["source_prim_type"],
        source_reference_sha256=snapshot["source_reference_sha256"],
        source_transform_authored_sha256=snapshot[
            "source_transform_authored_sha256"
        ],
        source_velocity_authored_sha256=snapshot["source_velocity_authored_sha256"],
        source_kinematic_enabled=snapshot["source_kinematic_enabled"],
        source_collision_filter_sha256=snapshot["source_collision_filter_sha256"],
        source_collision_api_sha256=snapshot["source_collision_api_sha256"],
        source_attachment_constraint_paths=snapshot[
            "source_attachment_constraint_paths"
        ],
        source_collider_inventory_sha256=snapshot["source_collider_inventory_sha256"],
    )


def evaluate_source_stage_authoring_diff(
    *, before: Mapping[str, Any], after: Mapping[str, Any]
) -> dict[str, Any]:
    """Fail closed if authored source state changes during a v2 child run."""

    first = _validate_source_stage_authoring_snapshot(before)
    second = _validate_source_stage_authoring_snapshot(after)
    if first["source_actor_path"] != second["source_actor_path"]:
        raise _error("source_stage", "source_actor_path_changed")
    fields = (
        "source_prim_type",
        "source_reference_sha256",
        "source_transform_authored_sha256",
        "source_velocity_authored_sha256",
        "source_kinematic_enabled",
        "source_collision_filter_sha256",
        "source_collision_api_sha256",
        "source_attachment_constraint_paths",
        "source_collider_inventory_sha256",
    )
    changed = [field for field in fields if first[field] != second[field]]
    payload = {
        "authority": "real_pbd_source_stage_authoring_diff_v1",
        "source_actor_path": first["source_actor_path"],
        "before_sha256": first["sha256"],
        "after_sha256": second["sha256"],
        "changed_fields": changed,
        "authoring_mutation_detected": bool(changed),
        "valid": not changed,
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


class ParticleRuntimeIdentityTracker:
    """Require an explicit stable particle-ID channel for G1-F evidence."""

    def __init__(self, *, expected_particle_ids: Sequence[int]) -> None:
        stage = "g1"
        if not isinstance(expected_particle_ids, Sequence) or isinstance(
            expected_particle_ids, (str, bytes, bytearray)
        ):
            raise _error(stage, "particle_ids_invalid")
        ids = []
        for value in expected_particle_ids:
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
                raise _error(stage, "particle_ids_invalid")
            identifier = int(value)
            if identifier < 0:
                raise _error(stage, "particle_ids_invalid")
            ids.append(identifier)
        if not ids or len(ids) != len(set(ids)):
            raise _error(stage, "particle_ids_invalid")
        self._expected_ids = tuple(sorted(ids))
        self._stable_ids_sha256 = canonical_json_sha256(
            {"particle_ids": list(self._expected_ids)}
        )
        self._last_physics_step: int | None = None
        self._readback_index = 0

    def observe(
        self,
        *,
        physics_step: int,
        particle_ids: Sequence[int],
        positions_world_m: Any,
        source_frame_pose_sha256: str,
    ) -> dict[str, Any]:
        stage = "g1"
        step = _nonnegative_index(physics_step, stage=stage, field="particle_physics_step")
        if self._last_physics_step is not None and step != self._last_physics_step + 1:
            raise _error(stage, "particle_identity_physics_step_invalid")
        if not isinstance(particle_ids, Sequence) or isinstance(
            particle_ids, (str, bytes, bytearray)
        ):
            raise _error(stage, "particle_ids_invalid")
        observed_ids = []
        for value in particle_ids:
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
                raise _error(stage, "particle_ids_invalid")
            identifier = int(value)
            if identifier < 0:
                raise _error(stage, "particle_ids_invalid")
            observed_ids.append(identifier)
        if len(observed_ids) != len(set(observed_ids)) or tuple(
            sorted(observed_ids)
        ) != self._expected_ids:
            raise _error(stage, "particle_ids_invalid")
        try:
            positions = np.asarray(positions_world_m, dtype=np.float64)
        except (TypeError, ValueError) as exc:
            raise _error(stage, "particle_positions_invalid") from exc
        if (
            positions.shape != (len(self._expected_ids), 3)
            or not np.isfinite(positions).all()
        ):
            raise _error(stage, "particle_positions_invalid")
        _sha256(source_frame_pose_sha256, stage=stage, field="source_frame_pose")
        positions_by_id = dict(zip(observed_ids, positions, strict=True))
        ordered_positions = np.asarray(
            [positions_by_id[identifier] for identifier in self._expected_ids],
            dtype=np.dtype("<f8"),
        )
        canonical_positions_sha256 = hashlib.sha256(
            np.ascontiguousarray(ordered_positions).tobytes(order="C")
        ).hexdigest()
        payload = {
            "authority": "real_pbd_runtime_particle_identity_receipt_v1",
            "physics_step": step,
            "readback_index": self._readback_index,
            "particle_count": len(self._expected_ids),
            "stable_ids_sha256": self._stable_ids_sha256,
            "canonical_positions_by_id_sha256": canonical_positions_sha256,
            "source_frame_pose_sha256": source_frame_pose_sha256,
            "coverage_complete": True,
        }
        self._last_physics_step = step
        self._readback_index += 1
        return {**payload, "sha256": canonical_json_sha256(payload)}


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _error("stage", "artifact_json_duplicate_key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise _error("stage", f"artifact_json_nonfinite_{value}")


def _validate_json_tree(value: Any) -> None:
    if isinstance(value, Mapping):
        for item in value.values():
            _validate_json_tree(item)
    elif isinstance(value, list):
        for item in value:
            _validate_json_tree(item)
    elif isinstance(value, float) and not math.isfinite(value):
        raise _error("stage", "artifact_json_nonfinite")


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise _error("stage", "artifact_json_invalid") from exc
    return (encoded + "\n").encode("utf-8")


def _stage_source_evidence(
    value: Any,
    *,
    stage: str,
    decision: str,
    fixture_identity_sha256: str,
    treatment_sha256: str,
) -> tuple[dict[str, Any], str]:
    if not isinstance(value, Mapping):
        raise _error("stage", "source_evidence_invalid")
    source = copy.deepcopy(dict(value))
    hash_fields = [field for field in ("sha256", "report_sha256") if field in source]
    if len(hash_fields) != 1:
        raise _error("stage", "source_evidence_invalid")
    hash_field = hash_fields[0]
    digest = source.pop(hash_field)
    _sha256(digest, stage="stage", field="source_evidence_sha256")
    if canonical_json_sha256(source) != digest:
        raise _error("stage", "source_evidence_hash_mismatch")
    source[hash_field] = digest
    authority = source.get("authority")
    source_decision = source.get("decision")
    if stage == "G0" and authority == "real_pbd_g0_runtime_capability_no_go_v2":
        checked = _hash_checked_mapping(
            source,
            stage="stage",
            authority="real_pbd_g0_runtime_capability_no_go_v2",
            hash_field="sha256",
        )
        if (
            source_decision != "G0_NO_GO"
            or checked.get("fixture_identity_sha256") != fixture_identity_sha256
            or checked.get("audit_spec_sha256") != treatment_sha256
            or checked.get("g2_eligible") is not False
            or checked.get("g3_g4_filled_load_authorized") is not False
            or checked.get("parent_recomputed") is not True
            or not isinstance(checked.get("checks"), Mapping)
            or not checked["checks"]
            or not isinstance(checked.get("no_go_reasons"), Sequence)
            or not checked["no_go_reasons"]
            or not _g0_runtime_parent_diagnostics_valid(checked)
        ):
            raise _error("stage", "source_evidence_binding_invalid")
    elif stage == "G0" and authority == "real_pbd_static_fixture_preflight_error_v1":
        if (
            source_decision != "G0_NO_GO"
            or source.get("asset_sha256") != fixture_identity_sha256
            or not isinstance(source.get("error"), str)
            or not source["error"]
        ):
            raise _error("stage", "source_evidence_binding_invalid")
    elif stage == "G0" and authority == "real_pbd_static_fixture_preflight_report_v1":
        evaluation = source.get("evaluation")
        if not isinstance(evaluation, Mapping):
            raise _error("stage", "source_evidence_identity_invalid")
        evaluated = _hash_checked_mapping(
            evaluation,
            stage="stage",
            authority="real_pbd_static_fixture_preflight_v1",
            hash_field="sha256",
        )
        source_decision = evaluated.get("g0_decision")
        if (
            source_decision != "G0_NO_GO"
            or source.get("usd_dependency_closure_sha256") != fixture_identity_sha256
            or evaluated.get("fixture_identity_sha256") != fixture_identity_sha256
        ):
            raise _error("stage", "source_evidence_binding_invalid")
    elif stage == "G0":
        if authority != "real_pbd_g0_clearance_decision_v1":
            raise _error("stage", "source_evidence_identity_invalid")
        checked = _hash_checked_mapping(
            source,
            stage="stage",
            authority="real_pbd_g0_clearance_decision_v1",
            hash_field="sha256",
        )
        fixture = checked.get("fixture_identity")
        checks = checked.get("checks")
        if (
            not isinstance(fixture, Mapping)
            or canonical_json_sha256(dict(fixture)) != fixture_identity_sha256
            or not isinstance(checks, Mapping)
            or not checks
            or any(type(result) is not bool for result in checks.values())
            or not isinstance(checked.get("selected_candidate_id"), str)
            or not checked["selected_candidate_id"]
        ):
            raise _error("stage", "source_evidence_binding_invalid")
        _sha256(checked.get("selected_candidate_sha256"), stage="stage", field="selected_candidate")
        _sha256(checked.get("certificate_sha256"), stage="stage", field="certificate")
        if (
            type(checked.get("g3_g4_filled_load_authorized")) is not bool
            or (decision == "G0_GO" and not all(checks.values()))
        ):
            raise _error("stage", "source_evidence_binding_invalid")
    elif stage in {"G1-D", "G1-F"}:
        expected_treatment = "dry" if stage == "G1-D" else "filled"
        if (
            authority != "real_pbd_g1_treatment_decision_v1"
            or source.get("treatment") != expected_treatment
        ):
            raise _error("stage", "source_evidence_identity_invalid")
        checked = _hash_checked_mapping(
            source,
            stage="stage",
            authority="real_pbd_g1_treatment_decision_v1",
            hash_field="sha256",
        )
        if (
            checked.get("fixture_lineage_sha256") != fixture_identity_sha256
            or type(checked.get("g2_eligible")) is not bool
            or type(checked.get("g3_g4_filled_load_authorized")) is not bool
            or not isinstance(checked.get("checks"), Mapping)
            or not checked["checks"]
            or (
                decision in {"G1_D_GO", "G1_F_GO"}
                and (
                    checked["g2_eligible"] is not True
                    or not all(value is True for value in checked["checks"].values())
                )
            )
        ):
            raise _error("stage", "source_evidence_binding_invalid")
    elif stage == "G1-COMPARE":
        if authority != "real_pbd_g1_baseline_comparison_v1":
            raise _error("stage", "source_evidence_identity_invalid")
        checked = _hash_checked_mapping(
            source,
            stage="stage",
            authority="real_pbd_g1_baseline_comparison_v1",
            hash_field="sha256",
        )
        if (
            checked.get("fixture_lineage_sha256") != fixture_identity_sha256
            or type(checked.get("g2_f_authorized")) is not bool
            or type(checked.get("g3_g4_filled_load_authorized")) is not bool
            or not isinstance(checked.get("checks"), Mapping)
            or not checked["checks"]
            or (
                decision == "G1_GO"
                and (
                    checked["g2_f_authorized"] is not True
                    or not all(value is True for value in checked["checks"].values())
                )
            )
        ):
            raise _error("stage", "source_evidence_binding_invalid")
    elif stage in {"G2-D", "G2-F"}:
        if authority != "real_pbd_g2_stage_decision_v1":
            raise _error("stage", "source_evidence_identity_invalid")
        checked = _hash_checked_mapping(
            source,
            stage="stage",
            authority="real_pbd_g2_stage_decision_v1",
            hash_field="sha256",
        )
        _sha256(
            checked.get("execution_context_sha256"),
            stage="stage",
            field="execution_context",
        )
        checks = checked.get("checks")
        if (
            not isinstance(checks, Mapping)
            or not checks
            or any(type(result) is not bool for result in checks.values())
            or (decision.endswith("_GO") and not all(checks.values()))
        ):
            raise _error("stage", "source_evidence_binding_invalid")
    if source_decision != decision:
        raise _error("stage", "source_evidence_decision_mismatch")
    return source, digest


def build_stage_evidence(
    *,
    stage: str,
    decision: str,
    fixture_identity_sha256: str,
    treatment_sha256: str,
    source_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind one typed stage decision to the canonical source evidence bytes."""

    if stage not in _STAGE_PREDECESSORS or decision not in _STAGE_ALLOWED_DECISIONS[stage]:
        raise _error("stage", "stage_evidence_identity_invalid")
    _sha256(fixture_identity_sha256, stage="stage", field="fixture_identity_sha256")
    _sha256(treatment_sha256, stage="stage", field="treatment_sha256")
    source, source_digest = _stage_source_evidence(
        source_evidence,
        stage=stage,
        decision=decision,
        fixture_identity_sha256=fixture_identity_sha256,
        treatment_sha256=treatment_sha256,
    )
    payload = {
        "authority": "real_pbd_stage_evidence_v1",
        "schema_version": 1,
        "stage": stage,
        "decision": decision,
        "fixture_identity_sha256": fixture_identity_sha256,
        "treatment_sha256": treatment_sha256,
        "source_evidence": source,
        "source_evidence_sha256": source_digest,
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


def _validate_stage_evidence(value: Any) -> dict[str, Any]:
    evidence = _hash_checked_mapping(
        value,
        stage="stage",
        authority="real_pbd_stage_evidence_v1",
        hash_field="sha256",
    )
    expected = {
        "authority",
        "schema_version",
        "stage",
        "decision",
        "fixture_identity_sha256",
        "treatment_sha256",
        "source_evidence",
        "source_evidence_sha256",
        "sha256",
    }
    if set(evidence) != expected or evidence["schema_version"] != 1:
        raise _error("stage", "stage_evidence_invalid")
    rebuilt = build_stage_evidence(
        stage=evidence["stage"],
        decision=evidence["decision"],
        fixture_identity_sha256=evidence["fixture_identity_sha256"],
        treatment_sha256=evidence["treatment_sha256"],
        source_evidence=evidence["source_evidence"],
    )
    if evidence != rebuilt:
        raise _error("stage", "stage_evidence_invalid")
    return evidence


def _validate_stage_artifact(value: Any) -> dict[str, Any]:
    stage = "stage"
    if not isinstance(value, Mapping):
        raise _error(stage, "artifact_mapping_required")
    artifact = copy.deepcopy(dict(value))
    digest = artifact.pop("artifact_sha256", None)
    _sha256(digest, stage=stage, field="artifact_sha256")
    required_fields = {
        "authority",
        "schema_version",
        "stage",
        "decision",
        "run_id",
        "reset_epoch",
        "fixture_identity_sha256",
        "treatment_sha256",
        "stage_evidence",
        "input_closure_sha256",
        "forbidden_frozen_v6_input_count",
        "predecessor_byte_hashes",
        "g2f_launch_binding",
    }
    if set(artifact) != required_fields:
        raise _error(stage, "artifact_fields_invalid")
    artifact_stage = artifact.get("stage")
    if (
        artifact.get("authority") != "real_pbd_stage_artifact_v1"
        or artifact.get("schema_version") != 1
        or artifact_stage not in _STAGE_PREDECESSORS
        or artifact.get("decision")
        not in _STAGE_ALLOWED_DECISIONS[artifact_stage]
    ):
        raise _error(stage, "artifact_identity_invalid")
    if not isinstance(artifact.get("run_id"), str) or not artifact["run_id"]:
        raise _error(stage, "run_id_invalid")
    _nonnegative_index(artifact.get("reset_epoch"), stage=stage, field="reset_epoch")
    for field in (
        "fixture_identity_sha256",
        "treatment_sha256",
        "input_closure_sha256",
    ):
        _sha256(artifact.get(field), stage=stage, field=field)
    evidence = _validate_stage_evidence(artifact.get("stage_evidence"))
    if (
        evidence["stage"] != artifact_stage
        or evidence["decision"] != artifact["decision"]
        or evidence["fixture_identity_sha256"] != artifact["fixture_identity_sha256"]
        or evidence["treatment_sha256"] != artifact["treatment_sha256"]
    ):
        raise _error(stage, "artifact_evidence_binding_invalid")
    launch_binding = artifact.get("g2f_launch_binding")
    if artifact_stage == "G2-F":
        binding = _validate_g2f_launch_binding(launch_binding)
        if (
            binding["successor_launch_manifest"]["successor_run_id"] != artifact["run_id"]
            or binding["successor_launch_manifest"]["successor_reset_epoch"]
            != artifact["reset_epoch"]
            or binding["authorization"]["fixture_identity_sha256"]
            != artifact["fixture_identity_sha256"]
            or binding["authorization"]["successor_treatment_sha256"]
            != artifact["treatment_sha256"]
            or artifact["predecessor_byte_hashes"]
            != {
                "G0": binding["parent_artifact_byte_hashes"]["G0"],
                "G1-COMPARE": binding["parent_artifact_byte_hashes"]["G1-COMPARE"],
                "G2-D": binding["parent_artifact_byte_hashes"]["G2-D"],
            }
        ):
            raise _error(stage, "artifact_authorization_invalid")
    elif launch_binding is not None:
        raise _error(stage, "artifact_authorization_invalid")
    frozen_count = artifact.get("forbidden_frozen_v6_input_count")
    if type(frozen_count) is not int or frozen_count != 0:
        raise _error(stage, "frozen_input_invalid")
    predecessors = artifact.get("predecessor_byte_hashes")
    expected_predecessors = set(_STAGE_PREDECESSORS[artifact_stage])
    if not isinstance(predecessors, Mapping) or set(predecessors) != expected_predecessors:
        raise _error(stage, "predecessor_hashes_invalid")
    normalized_predecessors = {
        name: _sha256(digest, stage=stage, field=f"predecessor_{name}")
        for name, digest in predecessors.items()
    }
    artifact["predecessor_byte_hashes"] = dict(sorted(normalized_predecessors.items()))
    if canonical_json_sha256(artifact) != digest:
        raise _error(stage, "artifact_hash_mismatch")
    return {**artifact, "artifact_sha256": digest}


def build_stage_artifact(
    *,
    stage: str,
    decision: str,
    run_id: str,
    reset_epoch: int,
    fixture_identity_sha256: str,
    treatment_sha256: str,
    stage_evidence: Mapping[str, Any],
    input_closure_sha256: str,
    forbidden_frozen_v6_input_count: int,
    predecessor_byte_hashes: Mapping[str, str],
    g2f_launch_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a canonical stage artifact; callers still publish it create-only."""

    if (
        stage not in _STAGE_PREDECESSORS
        or decision not in _STAGE_ALLOWED_DECISIONS[stage]
    ):
        raise _error("stage", "artifact_identity_invalid")
    if not isinstance(run_id, str) or not run_id:
        raise _error("stage", "run_id_invalid")
    _nonnegative_index(reset_epoch, stage="stage", field="reset_epoch")
    for field, value in (
        ("fixture_identity_sha256", fixture_identity_sha256),
        ("treatment_sha256", treatment_sha256),
        ("input_closure_sha256", input_closure_sha256),
    ):
        _sha256(value, stage="stage", field=field)
    if type(forbidden_frozen_v6_input_count) is not int or forbidden_frozen_v6_input_count != 0:
        raise _error("stage", "frozen_input_invalid")
    expected_predecessors = set(_STAGE_PREDECESSORS[stage])
    if (
        not isinstance(predecessor_byte_hashes, Mapping)
        or set(predecessor_byte_hashes) != expected_predecessors
    ):
        raise _error("stage", "predecessor_hashes_invalid")
    predecessors = {
        name: _sha256(value, stage="stage", field=f"predecessor_{name}")
        for name, value in predecessor_byte_hashes.items()
    }
    evidence = _validate_stage_evidence(stage_evidence)
    if (
        evidence["stage"] != stage
        or evidence["decision"] != decision
        or evidence["fixture_identity_sha256"] != fixture_identity_sha256
        or evidence["treatment_sha256"] != treatment_sha256
    ):
        raise _error("stage", "artifact_evidence_binding_invalid")
    if stage == "G2-F":
        binding = _validate_g2f_launch_binding(g2f_launch_binding)
        if (
            binding["successor_launch_manifest"]["successor_run_id"] != run_id
            or binding["successor_launch_manifest"]["successor_reset_epoch"] != reset_epoch
            or binding["authorization"]["fixture_identity_sha256"] != fixture_identity_sha256
            or binding["authorization"]["successor_treatment_sha256"] != treatment_sha256
            or predecessors
            != {
                "G0": binding["parent_artifact_byte_hashes"]["G0"],
                "G1-COMPARE": binding["parent_artifact_byte_hashes"]["G1-COMPARE"],
                "G2-D": binding["parent_artifact_byte_hashes"]["G2-D"],
            }
        ):
            raise _error("stage", "artifact_authorization_invalid")
    elif g2f_launch_binding is not None:
        raise _error("stage", "artifact_authorization_invalid")
    payload = {
        "authority": "real_pbd_stage_artifact_v1",
        "schema_version": 1,
        "stage": stage,
        "decision": decision,
        "run_id": run_id,
        "reset_epoch": reset_epoch,
        "fixture_identity_sha256": fixture_identity_sha256,
        "treatment_sha256": treatment_sha256,
        "stage_evidence": evidence,
        "input_closure_sha256": input_closure_sha256,
        "forbidden_frozen_v6_input_count": 0,
        "predecessor_byte_hashes": dict(sorted(predecessors.items())),
        "g2f_launch_binding": g2f_launch_binding,
    }
    return {**payload, "artifact_sha256": canonical_json_sha256(payload)}


def serialize_stage_artifact(artifact: Mapping[str, Any]) -> bytes:
    """Serialize one canonical artifact for a create-only parent-owned file."""

    checked = _validate_stage_artifact(artifact)
    return _canonical_json_bytes(checked)


def _parse_stage_artifact_bytes(value: Any) -> tuple[dict[str, Any], str]:
    if not isinstance(value, bytes) or not value or not value.endswith(b"\n"):
        raise _error("stage", "artifact_bytes_invalid")
    try:
        decoded = value.decode("utf-8", errors="strict")
        parsed = json.loads(
            decoded,
            object_pairs_hook=_strict_object_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise _error("stage", "artifact_bytes_invalid") from exc
    _validate_json_tree(parsed)
    artifact = _validate_stage_artifact(parsed)
    if value != _canonical_json_bytes(artifact):
        raise _error("stage", "artifact_bytes_noncanonical")
    return artifact, hashlib.sha256(value).hexdigest()


def _parent_artifacts_for_g2f(value: Any) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    stage = "g2f"
    required = ("G0", "G1-D", "G1-F", "G1-COMPARE", "G2-D")
    if not isinstance(value, Mapping) or set(value) != set(required):
        raise _error(stage, "parent_artifacts_invalid")
    artifacts: dict[str, dict[str, Any]] = {}
    byte_hashes: dict[str, str] = {}
    for name in required:
        artifact, byte_hash = _parse_stage_artifact_bytes(value[name])
        if (
            artifact["stage"] != name
            or artifact["decision"] != _STAGE_GO_DECISIONS[name]
        ):
            raise _error(stage, "parent_lineage_invalid")
        artifacts[name] = artifact
        byte_hashes[name] = byte_hash
    if len({artifact["fixture_identity_sha256"] for artifact in artifacts.values()}) != 1:
        raise _error(stage, "parent_lineage_invalid")
    expected_parent_hashes = {
        "G1-D": {"G0": byte_hashes["G0"]},
        "G1-F": {"G0": byte_hashes["G0"]},
        "G1-COMPARE": {
            "G1-D": byte_hashes["G1-D"],
            "G1-F": byte_hashes["G1-F"],
        },
        "G2-D": {
            "G0": byte_hashes["G0"],
            "G1-COMPARE": byte_hashes["G1-COMPARE"],
        },
    }
    if any(
        artifacts[name]["predecessor_byte_hashes"] != expected
        for name, expected in expected_parent_hashes.items()
    ):
        raise _error(stage, "parent_lineage_invalid")
    return artifacts, dict(sorted(byte_hashes.items()))


def _validate_g2f_authorization(value: Any) -> dict[str, Any]:
    stage = "g2f"
    if not isinstance(value, Mapping):
        raise _error(stage, "authorization_invalid")
    authorization = copy.deepcopy(dict(value))
    digest = authorization.pop("authorization_sha256", None)
    _sha256(digest, stage=stage, field="authorization_sha256")
    expected_fields = {
        "authority",
        "schema_version",
        "successor_stage",
        "successor_treatment_sha256",
        "fixture_identity_sha256",
        "parent_artifact_byte_hashes",
        "authorization_id",
        "ledger_key_sha256",
    }
    if (
        set(authorization) != expected_fields
        or authorization.get("authority") != "real_pbd_g2f_one_use_authorization_v1"
        or authorization.get("schema_version") != 1
        or authorization.get("successor_stage") != "G2-F"
    ):
        raise _error(stage, "authorization_invalid")
    for field in (
        "successor_treatment_sha256",
        "fixture_identity_sha256",
        "authorization_id",
        "ledger_key_sha256",
    ):
        _sha256(authorization.get(field), stage=stage, field=field)
    hashes = authorization.get("parent_artifact_byte_hashes")
    required = {"G0", "G1-D", "G1-F", "G1-COMPARE", "G2-D"}
    if not isinstance(hashes, Mapping) or set(hashes) != required:
        raise _error(stage, "authorization_invalid")
    normalized_hashes = {
        name: _sha256(value, stage=stage, field=f"parent_{name}")
        for name, value in hashes.items()
    }
    authorization["parent_artifact_byte_hashes"] = dict(sorted(normalized_hashes.items()))
    ledger_input = {
        "fixture_identity_sha256": authorization["fixture_identity_sha256"],
        "parent_artifact_byte_hashes": authorization["parent_artifact_byte_hashes"],
        "successor_stage": "G2-F",
        "successor_treatment_sha256": authorization["successor_treatment_sha256"],
    }
    if (
        authorization["ledger_key_sha256"] != canonical_json_sha256(ledger_input)
        or digest != canonical_json_sha256(authorization)
    ):
        raise _error(stage, "authorization_hash_mismatch")
    return {**authorization, "authorization_sha256": digest}


def build_g2f_one_use_authorization(
    *,
    parent_artifact_bytes: Mapping[str, bytes],
    successor_treatment_sha256: str,
    authorization_id: str,
) -> dict[str, Any]:
    """Bind a fresh G2-F launch to the exact sealed G0/G1/G2-D byte chain."""

    artifacts, parent_hashes = _parent_artifacts_for_g2f(parent_artifact_bytes)
    _sha256(
        successor_treatment_sha256,
        stage="g2f",
        field="successor_treatment_sha256",
    )
    _sha256(authorization_id, stage="g2f", field="authorization_id")
    fixture_identity = artifacts["G0"]["fixture_identity_sha256"]
    ledger_input = {
        "fixture_identity_sha256": fixture_identity,
        "parent_artifact_byte_hashes": parent_hashes,
        "successor_stage": "G2-F",
        "successor_treatment_sha256": successor_treatment_sha256,
    }
    payload = {
        "authority": "real_pbd_g2f_one_use_authorization_v1",
        "schema_version": 1,
        "successor_stage": "G2-F",
        "successor_treatment_sha256": successor_treatment_sha256,
        "fixture_identity_sha256": fixture_identity,
        "parent_artifact_byte_hashes": parent_hashes,
        "authorization_id": authorization_id,
        "ledger_key_sha256": canonical_json_sha256(ledger_input),
    }
    return {
        **payload,
        "authorization_sha256": canonical_json_sha256(payload),
    }


def _g2f_validate_parent_binding(
    *, authorization: Mapping[str, Any], parent_artifact_bytes: Mapping[str, bytes]
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    artifacts, parent_hashes = _parent_artifacts_for_g2f(parent_artifact_bytes)
    if (
        parent_hashes != authorization["parent_artifact_byte_hashes"]
        or artifacts["G0"]["fixture_identity_sha256"]
        != authorization["fixture_identity_sha256"]
    ):
        raise _error("g2f", "parent_artifact_binding_invalid")
    return artifacts, parent_hashes


def build_g2f_successor_launch_manifest(
    *,
    authorization: Mapping[str, Any],
    parent_artifact_bytes: Mapping[str, bytes],
    successor_run_id: str,
    successor_reset_epoch: int,
) -> dict[str, Any]:
    """Seal the child launch against the exact parents before consuming G2-F."""

    checked = _validate_g2f_authorization(authorization)
    _, parent_hashes = _g2f_validate_parent_binding(
        authorization=checked, parent_artifact_bytes=parent_artifact_bytes
    )
    if not isinstance(successor_run_id, str) or not successor_run_id:
        raise _error("g2f", "successor_run_id_invalid")
    reset_epoch = _nonnegative_index(
        successor_reset_epoch, stage="g2f", field="successor_reset_epoch"
    )
    payload = {
        "authority": "real_pbd_g2f_successor_launch_manifest_v1",
        "schema_version": 1,
        "successor_stage": "G2-F",
        "successor_run_id": successor_run_id,
        "successor_reset_epoch": reset_epoch,
        "successor_treatment_sha256": checked["successor_treatment_sha256"],
        "fixture_identity_sha256": checked["fixture_identity_sha256"],
        "parent_artifact_byte_hashes": parent_hashes,
        "authorization_sha256": checked["authorization_sha256"],
        "ledger_key_sha256": checked["ledger_key_sha256"],
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


def _validate_g2f_successor_launch_manifest(
    value: Any, *, authorization: Mapping[str, Any], parent_hashes: Mapping[str, str]
) -> dict[str, Any]:
    manifest = _hash_checked_mapping(
        value,
        stage="g2f",
        authority="real_pbd_g2f_successor_launch_manifest_v1",
        hash_field="sha256",
    )
    expected = {
        "authority",
        "schema_version",
        "successor_stage",
        "successor_run_id",
        "successor_reset_epoch",
        "successor_treatment_sha256",
        "fixture_identity_sha256",
        "parent_artifact_byte_hashes",
        "authorization_sha256",
        "ledger_key_sha256",
        "sha256",
    }
    if (
        set(manifest) != expected
        or manifest["schema_version"] != 1
        or manifest["successor_stage"] != "G2-F"
        or not isinstance(manifest["successor_run_id"], str)
        or not manifest["successor_run_id"]
    ):
        raise _error("g2f", "successor_launch_manifest_invalid")
    _nonnegative_index(
        manifest["successor_reset_epoch"], stage="g2f", field="successor_reset_epoch"
    )
    if (
        manifest["successor_treatment_sha256"] != authorization["successor_treatment_sha256"]
        or manifest["fixture_identity_sha256"] != authorization["fixture_identity_sha256"]
        or manifest["parent_artifact_byte_hashes"] != parent_hashes
        or manifest["authorization_sha256"] != authorization["authorization_sha256"]
        or manifest["ledger_key_sha256"] != authorization["ledger_key_sha256"]
    ):
        raise _error("g2f", "successor_launch_manifest_binding_invalid")
    return manifest


def consume_g2f_one_use_authorization(
    *,
    authorization: Mapping[str, Any],
    parent_artifact_bytes: Mapping[str, bytes],
    successor_launch_manifest: Mapping[str, Any],
    ledger_directory: str | os.PathLike[str],
) -> dict[str, Any]:
    """Atomically consume a launch bound to the exact parent artifact bytes."""

    checked = _validate_g2f_authorization(authorization)
    _, parent_hashes = _g2f_validate_parent_binding(
        authorization=checked, parent_artifact_bytes=parent_artifact_bytes
    )
    launch_manifest = _validate_g2f_successor_launch_manifest(
        successor_launch_manifest,
        authorization=checked,
        parent_hashes=parent_hashes,
    )
    directory = Path(ledger_directory)
    try:
        directory_stat = os.lstat(directory)
    except OSError as exc:
        raise _error("g2f", "authorization_ledger_directory_invalid") from exc
    if stat.S_ISLNK(directory_stat.st_mode) or not stat.S_ISDIR(directory_stat.st_mode):
        raise _error("g2f", "authorization_ledger_directory_invalid")
    filename = f"{checked['ledger_key_sha256']}.json"
    output = directory / filename
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        directory_descriptor = os.open(directory, directory_flags)
    except OSError as exc:
        raise _error("g2f", "authorization_ledger_directory_invalid") from exc
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    temporary_name = f".{filename}.{secrets.token_hex(16)}.tmp"
    linked = False
    try:
        try:
            descriptor = os.open(
                temporary_name, flags, 0o600, dir_fd=directory_descriptor
            )
        except OSError as exc:
            raise _error("g2f", "authorization_ledger_create_failed") from exc
        payload = _canonical_json_bytes(
            {
                "authorization": checked,
                "successor_launch_manifest": launch_manifest,
            }
        )
        try:
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise OSError("authorization_ledger_write_failed")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            os.link(
                temporary_name,
                filename,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            linked = True
        except FileExistsError as exc:
            raise _error("g2f", "authorization_already_consumed") from exc
        except OSError as exc:
            raise _error("g2f", "authorization_ledger_create_failed") from exc
        try:
            os.unlink(temporary_name, dir_fd=directory_descriptor)
            os.fsync(directory_descriptor)
        except OSError as exc:
            raise _error("g2f", "authorization_durability_indeterminate") from exc
    finally:
        if not linked:
            try:
                os.unlink(temporary_name, dir_fd=directory_descriptor)
            except FileNotFoundError:
                pass
            except OSError:
                pass
        os.close(directory_descriptor)
    result = {
        "authority": "real_pbd_g2f_one_use_authorization_consumption_v1",
        "authorization_sha256": checked["authorization_sha256"],
        "successor_launch_manifest_sha256": launch_manifest["sha256"],
        "ledger_key_sha256": checked["ledger_key_sha256"],
        "ledger_path": str(output),
        "consumed": True,
    }
    return {**result, "sha256": canonical_json_sha256(result)}


def _validate_g2f_consumption_receipt(
    value: Any, *, authorization: Mapping[str, Any], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    receipt = _hash_checked_mapping(
        value,
        stage="g2f",
        authority="real_pbd_g2f_one_use_authorization_consumption_v1",
        hash_field="sha256",
    )
    expected = {
        "authority", "authorization_sha256", "successor_launch_manifest_sha256",
        "ledger_key_sha256", "ledger_path", "consumed", "sha256",
    }
    if (
        set(receipt) != expected
        or receipt["authorization_sha256"] != authorization["authorization_sha256"]
        or receipt["successor_launch_manifest_sha256"] != manifest["sha256"]
        or receipt["ledger_key_sha256"] != authorization["ledger_key_sha256"]
        or not isinstance(receipt["ledger_path"], str)
        or not receipt["ledger_path"]
        or receipt["consumed"] is not True
    ):
        raise _error("g2f", "consumption_receipt_invalid")
    ledger_path = Path(receipt["ledger_path"])
    try:
        ledger_stat = os.lstat(ledger_path)
    except OSError as exc:
        raise _error("g2f", "consumption_receipt_ledger_missing") from exc
    if (
        stat.S_ISLNK(ledger_stat.st_mode)
        or not stat.S_ISREG(ledger_stat.st_mode)
        or ledger_stat.st_nlink != 1
        or ledger_path.name != f"{authorization['ledger_key_sha256']}.json"
    ):
        raise _error("g2f", "consumption_receipt_ledger_invalid")
    try:
        descriptor = os.open(
            ledger_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        )
    except OSError as exc:
        raise _error("g2f", "consumption_receipt_ledger_invalid") from exc
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
        decoded = payload.decode("utf-8", errors="strict")
        ledger = json.loads(
            decoded,
            object_pairs_hook=_strict_object_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise _error("g2f", "consumption_receipt_ledger_invalid") from exc
    _validate_json_tree(ledger)
    expected_ledger = {
        "authorization": dict(authorization),
        "successor_launch_manifest": dict(manifest),
    }
    if payload != _canonical_json_bytes(expected_ledger) or ledger != expected_ledger:
        raise _error("g2f", "consumption_receipt_ledger_invalid")
    return receipt


def build_g2f_launch_binding(
    *,
    authorization: Mapping[str, Any],
    parent_artifact_bytes: Mapping[str, bytes],
    successor_launch_manifest: Mapping[str, Any],
    consumption_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind the final G2-F artifact to the consumed authorization transaction."""

    checked = _validate_g2f_authorization(authorization)
    _, parent_hashes = _g2f_validate_parent_binding(
        authorization=checked, parent_artifact_bytes=parent_artifact_bytes
    )
    manifest = _validate_g2f_successor_launch_manifest(
        successor_launch_manifest, authorization=checked, parent_hashes=parent_hashes
    )
    consumption = _validate_g2f_consumption_receipt(
        consumption_receipt, authorization=checked, manifest=manifest
    )
    payload = {
        "authority": "real_pbd_g2f_launch_binding_v1",
        "schema_version": 1,
        "authorization": checked,
        "parent_artifact_byte_hashes": parent_hashes,
        "successor_launch_manifest": manifest,
        "consumption_receipt": consumption,
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


def _validate_g2f_launch_binding(value: Any) -> dict[str, Any]:
    binding = _hash_checked_mapping(
        value,
        stage="g2f",
        authority="real_pbd_g2f_launch_binding_v1",
        hash_field="sha256",
    )
    expected = {
        "authority", "schema_version", "authorization", "parent_artifact_byte_hashes",
        "successor_launch_manifest", "consumption_receipt", "sha256",
    }
    if set(binding) != expected or binding["schema_version"] != 1:
        raise _error("g2f", "launch_binding_invalid")
    authorization = _validate_g2f_authorization(binding["authorization"])
    parent_hashes = authorization["parent_artifact_byte_hashes"]
    if binding["parent_artifact_byte_hashes"] != parent_hashes:
        raise _error("g2f", "launch_binding_invalid")
    manifest = _validate_g2f_successor_launch_manifest(
        binding["successor_launch_manifest"],
        authorization=authorization,
        parent_hashes=parent_hashes,
    )
    consumption = _validate_g2f_consumption_receipt(
        binding["consumption_receipt"], authorization=authorization, manifest=manifest
    )
    if binding["consumption_receipt"] != consumption:
        raise _error("g2f", "launch_binding_invalid")
    return binding
