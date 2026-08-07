"""Pure-Python diagnostic contract for wrapper-to-hand filter observations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


_AUTHORITY = "nonformal_wrapper_franka_collision_filter_proof_v1"
_CLASSIFICATION = "NON_FORMAL_OBSERVATION_ONLY"
_SCHEMA_VERSION = 1
_SELECTED_HAND_BODY_PATH = "/World/Franka/panda_hand"
_SOURCE_MESH_PATH = "/World/beaker2/mesh"
_WRAPPER_ROOT_PATH = "/World/beaker2/FluidSafeWrapperCanonical"
_UNFILTERED_VARIANT = "scoped_unfiltered_qualification"
_AUTHORED_VARIANT = "authored_filter_confirmation"
_VARIANTS = (_UNFILTERED_VARIANT, _AUTHORED_VARIANT)
_SHA256_CHARACTERS = frozenset("0123456789abcdef")
_CONTRACT_PAYLOAD_FIELDS = frozenset(
    {
        "authority",
        "classification",
        "schema_version",
        "v7_config_sha256",
        "local_scene_sha256",
        "local_franka_sha256",
        "cube_overlay_sha256",
        "selected_hand_body_path",
        "source_mesh_path",
        "wrapper_root_path",
        "variants",
    }
)
_CONTRACT_FIELDS = _CONTRACT_PAYLOAD_FIELDS | {"sha256"}
_HEADER_FIELDS = frozenset({"type", "actor0", "actor1", "collider0", "collider1"})
_CONTACT_TYPES = frozenset({"FOUND", "PERSIST", "LOST"})
_ACTIVE_CONTACT_TYPES = frozenset({"FOUND", "PERSIST"})
_VARIANT_FIELDS = frozenset(
    {
        "variant",
        "selected_hand_collider",
        "source_mesh_colliders",
        "wrapper_colliders",
        "transform_plan_sha256",
        "runtime_identity_sha256",
        "reports",
    }
)


def canonical_json_sha256(value: Any) -> str:
    """Return the SHA-256 digest of deterministic, ASCII JSON."""
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("nonformal_collision_filter_proof_json_invalid") from exc
    return hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _SHA256_CHARACTERS for character in value)
    )


def _require_sha256(value: Any, *, field: str) -> str:
    if not _is_sha256(value):
        raise ValueError(f"nonformal_collision_filter_proof_{field}_invalid")
    return value


def _is_normalized_absolute_path(value: Any) -> bool:
    if (
        not isinstance(value, str)
        or not value.isascii()
        or value == "/"
        or not value.startswith("/")
        or value.endswith("/")
        or "//" in value
    ):
        return False
    return all(part not in {"", ".", ".."} for part in value.split("/")[1:])


def _path_is_at_or_below(path: str, root: str) -> bool:
    return path == root or path.startswith(f"{root}/")


def _is_strict_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    )


def _normalize_collider_inventory(
    value: Any,
    *,
    root_path: str,
    field: str,
) -> list[str]:
    if not _is_strict_sequence(value) or not value:
        raise ValueError(f"nonformal_collision_filter_proof_{field}_invalid")
    colliders = list(value)
    if (
        any(not _is_normalized_absolute_path(collider) for collider in colliders)
        or any(not _path_is_at_or_below(collider, root_path) for collider in colliders)
        or len(colliders) != len(set(colliders))
    ):
        raise ValueError(f"nonformal_collision_filter_proof_{field}_invalid")
    return sorted(colliders)


def _normalize_selected_hand_collider(value: Any) -> str:
    if not _is_normalized_absolute_path(value) or not _path_is_at_or_below(
        value, _SELECTED_HAND_BODY_PATH
    ):
        raise ValueError(
            "nonformal_collision_filter_proof_selected_hand_collider_invalid"
        )
    return value


def _normalize_header(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or frozenset(value) != _HEADER_FIELDS:
        raise ValueError("nonformal_collision_filter_proof_header_invalid")
    header = dict(value)
    if not isinstance(header["type"], str) or header["type"] not in _CONTACT_TYPES:
        raise ValueError("nonformal_collision_filter_proof_type_invalid")
    normalized = {
        "type": header["type"],
        "actor0": header["actor0"],
        "actor1": header["actor1"],
        "collider0": header["collider0"],
        "collider1": header["collider1"],
    }
    if any(
        not _is_normalized_absolute_path(normalized[field])
        for field in ("actor0", "actor1", "collider0", "collider1")
    ):
        raise ValueError("nonformal_collision_filter_proof_header_invalid")
    return normalized


def _canonical_pair(collider0: str, collider1: str) -> tuple[str, str]:
    return tuple(sorted((collider0, collider1)))


def _pairs_as_lists(pairs: set[tuple[str, str]]) -> list[list[str]]:
    return [list(pair) for pair in sorted(pairs)]


def _unique_failures(failures: list[str]) -> list[str]:
    return list(dict.fromkeys(failures))


def validate_filter_proof_contract(value: Any) -> dict[str, Any]:
    """Validate the sealed, exact Phase 1 diagnostic contract payload."""
    if not isinstance(value, Mapping):
        raise ValueError("nonformal_collision_filter_proof_contract_invalid")
    raw = dict(value)
    if frozenset(raw) != _CONTRACT_FIELDS:
        raise ValueError("nonformal_collision_filter_proof_contract_fields_invalid")
    if raw["authority"] != _AUTHORITY:
        raise ValueError("nonformal_collision_filter_proof_contract_authority_invalid")
    if raw["classification"] != _CLASSIFICATION:
        raise ValueError(
            "nonformal_collision_filter_proof_contract_classification_invalid"
        )
    if type(raw["schema_version"]) is not int or raw["schema_version"] != _SCHEMA_VERSION:
        raise ValueError(
            "nonformal_collision_filter_proof_contract_schema_version_invalid"
        )

    v7_config_sha256 = _require_sha256(
        raw["v7_config_sha256"], field="v7_config_sha256"
    )
    local_scene_sha256 = _require_sha256(
        raw["local_scene_sha256"], field="local_scene_sha256"
    )
    local_franka_sha256 = _require_sha256(
        raw["local_franka_sha256"], field="local_franka_sha256"
    )
    cube_overlay_sha256 = _require_sha256(
        raw["cube_overlay_sha256"], field="cube_overlay_sha256"
    )
    if raw["selected_hand_body_path"] != _SELECTED_HAND_BODY_PATH:
        raise ValueError(
            "nonformal_collision_filter_proof_selected_hand_body_path_invalid"
        )
    if raw["source_mesh_path"] != _SOURCE_MESH_PATH:
        raise ValueError("nonformal_collision_filter_proof_source_mesh_path_invalid")
    if raw["wrapper_root_path"] != _WRAPPER_ROOT_PATH:
        raise ValueError("nonformal_collision_filter_proof_wrapper_root_path_invalid")
    if not isinstance(raw["variants"], list) or raw["variants"] != list(_VARIANTS):
        raise ValueError("nonformal_collision_filter_proof_variants_invalid")

    payload = {
        "authority": _AUTHORITY,
        "classification": _CLASSIFICATION,
        "schema_version": _SCHEMA_VERSION,
        "v7_config_sha256": v7_config_sha256,
        "local_scene_sha256": local_scene_sha256,
        "local_franka_sha256": local_franka_sha256,
        "cube_overlay_sha256": cube_overlay_sha256,
        "selected_hand_body_path": _SELECTED_HAND_BODY_PATH,
        "source_mesh_path": _SOURCE_MESH_PATH,
        "wrapper_root_path": _WRAPPER_ROOT_PATH,
        "variants": list(_VARIANTS),
    }
    digest = _require_sha256(raw["sha256"], field="contract_sha256")
    if digest != canonical_json_sha256(payload):
        raise ValueError("nonformal_collision_filter_proof_contract_sha256_mismatch")
    return {**payload, "sha256": digest}


def evaluate_variant_contacts(
    variant: Any,
    selected_hand_collider: Any,
    source_mesh_colliders: Any,
    wrapper_colliders: Any,
    reports: Any,
) -> dict[str, Any]:
    """Audit one variant's normalized contact headers without making a gate claim.

    Only active FOUND/PERSIST headers can qualify a pair. Counts are unique
    collider-pair counts, so repeated lifecycle headers for a pair do not
    inflate the qualification result.
    """
    failures: list[str] = []
    if variant not in _VARIANTS:
        failures.append("variant_invalid")

    hand_collider: str | None = None
    source_colliders: list[str] = []
    wrapper_collider_paths: list[str] = []
    try:
        hand_collider = _normalize_selected_hand_collider(selected_hand_collider)
    except ValueError:
        failures.append("selected_hand_collider_invalid")
    try:
        source_colliders = _normalize_collider_inventory(
            source_mesh_colliders,
            root_path=_SOURCE_MESH_PATH,
            field="source_mesh_colliders",
        )
    except ValueError:
        failures.append("source_mesh_colliders_invalid")
    try:
        wrapper_collider_paths = _normalize_collider_inventory(
            wrapper_colliders,
            root_path=_WRAPPER_ROOT_PATH,
            field="wrapper_colliders",
        )
    except ValueError:
        failures.append("wrapper_colliders_invalid")

    source_set = set(source_colliders)
    wrapper_set = set(wrapper_collider_paths)
    source_actor_path = _SOURCE_MESH_PATH.rsplit("/", 1)[0]
    if source_set.intersection(wrapper_set):
        failures.append("collider_inventory_partition_invalid")

    normalized_headers: list[dict[str, str]] = []
    if not _is_strict_sequence(reports):
        failures.append("reports_not_strict_sequence")
        report_values: Sequence[Any] = ()
    else:
        report_values = reports
    for index, report in enumerate(report_values):
        try:
            normalized_headers.append(_normalize_header(report))
        except ValueError as exc:
            message = str(exc).removeprefix("nonformal_collision_filter_proof_")
            failures.append(f"report_{index}_{message}")

    observed_pairs: set[tuple[str, str]] = set()
    source_pairs: set[tuple[str, str]] = set()
    wrapper_pairs: set[tuple[str, str]] = set()
    for header in normalized_headers:
        collider0 = header["collider0"]
        collider1 = header["collider1"]
        pair = _canonical_pair(collider0, collider1)
        observed_pairs.add(pair)
        if hand_collider is not None and header["type"] in _ACTIVE_CONTACT_TYPES:
            selected_pair = (
                collider0 == hand_collider
                and (collider1 in source_set or collider1 in wrapper_set)
            ) or (
                collider1 == hand_collider
                and (collider0 in source_set or collider0 in wrapper_set)
            )
            if selected_pair and {
                header["actor0"],
                header["actor1"],
            } != {_SELECTED_HAND_BODY_PATH, source_actor_path}:
                failures.append("selected_hand_contact_actor_pair_invalid")
                continue
            if collider0 == hand_collider and collider1 in source_set:
                source_pairs.add(pair)
            elif collider1 == hand_collider and collider0 in source_set:
                source_pairs.add(pair)
            if collider0 == hand_collider and collider1 in wrapper_set:
                wrapper_pairs.add(pair)
            elif collider1 == hand_collider and collider0 in wrapper_set:
                wrapper_pairs.add(pair)

    if not source_pairs:
        failures.append("selected_hand_source_mesh_contact_missing")
    if variant == _UNFILTERED_VARIANT and not wrapper_pairs:
        failures.append("selected_hand_wrapper_contact_count_invalid")
    elif variant == _AUTHORED_VARIANT and wrapper_pairs:
        failures.append("selected_hand_wrapper_contact_unexpected")

    return {
        "variant": variant if variant in _VARIANTS else None,
        "audit_valid": not failures,
        "source_mesh_contact_observed": bool(source_pairs),
        "source_mesh_contact_count": len(source_pairs),
        "wrapper_contact_observed": bool(wrapper_pairs),
        "wrapper_contact_count": len(wrapper_pairs),
        "source_mesh_contact_pairs": _pairs_as_lists(source_pairs),
        "wrapper_contact_pairs": _pairs_as_lists(wrapper_pairs),
        "observed_pairs": _pairs_as_lists(observed_pairs),
        "failures": _unique_failures(failures),
    }


def _normalize_variant_observation(
    value: Any,
    *,
    expected_variant: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("nonformal_collision_filter_proof_variant_invalid")
    raw = dict(value)
    if frozenset(raw) != _VARIANT_FIELDS:
        raise ValueError("nonformal_collision_filter_proof_variant_fields_invalid")
    if raw["variant"] != expected_variant:
        raise ValueError("nonformal_collision_filter_proof_variant_name_invalid")
    return {
        "variant": expected_variant,
        "selected_hand_collider": _normalize_selected_hand_collider(
            raw["selected_hand_collider"]
        ),
        "source_mesh_colliders": _normalize_collider_inventory(
            raw["source_mesh_colliders"],
            root_path=_SOURCE_MESH_PATH,
            field="source_mesh_colliders",
        ),
        "wrapper_colliders": _normalize_collider_inventory(
            raw["wrapper_colliders"],
            root_path=_WRAPPER_ROOT_PATH,
            field="wrapper_colliders",
        ),
        "transform_plan_sha256": _require_sha256(
            raw["transform_plan_sha256"], field="transform_plan_sha256"
        ),
        "runtime_identity_sha256": _require_sha256(
            raw["runtime_identity_sha256"], field="runtime_identity_sha256"
        ),
        "reports": raw["reports"],
    }


def _diagnostic_outcome(outcome: str, failures: list[str]) -> dict[str, Any]:
    return {"outcome": outcome, "failures": _unique_failures(failures)}


def evaluate_ab_filter_proof(
    contract: Any,
    unfiltered: Any,
    authored: Any,
) -> dict[str, Any]:
    """Compare the two contact variants using only diagnostic outcomes.

    Runtime bindings and inventories must match before contact observations can
    be compared. A matching, valid B/A contact matrix is still only a non-formal
    observation of filter behavior.
    """
    try:
        validate_filter_proof_contract(contract)
    except ValueError:
        return _diagnostic_outcome(
            "RUNTIME_BLOCKED", ["filter_proof_contract_invalid"]
        )

    variant_failures: list[str] = []
    try:
        normalized_unfiltered = _normalize_variant_observation(
            unfiltered, expected_variant=_UNFILTERED_VARIANT
        )
    except ValueError:
        variant_failures.append("unfiltered_variant_invalid")
        normalized_unfiltered = None
    try:
        normalized_authored = _normalize_variant_observation(
            authored, expected_variant=_AUTHORED_VARIANT
        )
    except ValueError:
        variant_failures.append("authored_variant_invalid")
        normalized_authored = None
    if variant_failures:
        return _diagnostic_outcome("RUNTIME_BLOCKED", variant_failures)

    assert normalized_unfiltered is not None
    assert normalized_authored is not None
    comparison_fields = (
        ("selected_hand_collider", "selected_hand_collider_mismatch"),
        (
            "source_mesh_colliders",
            "source_mesh_collider_inventory_mismatch",
        ),
        ("wrapper_colliders", "wrapper_collider_inventory_mismatch"),
        ("transform_plan_sha256", "transform_plan_sha256_mismatch"),
        ("runtime_identity_sha256", "runtime_identity_sha256_mismatch"),
    )
    binding_failures = [
        failure
        for field, failure in comparison_fields
        if normalized_unfiltered[field] != normalized_authored[field]
    ]
    if binding_failures:
        return _diagnostic_outcome("RUNTIME_BLOCKED", binding_failures)

    unfiltered_audit = evaluate_variant_contacts(
        normalized_unfiltered["variant"],
        normalized_unfiltered["selected_hand_collider"],
        normalized_unfiltered["source_mesh_colliders"],
        normalized_unfiltered["wrapper_colliders"],
        normalized_unfiltered["reports"],
    )
    authored_audit = evaluate_variant_contacts(
        normalized_authored["variant"],
        normalized_authored["selected_hand_collider"],
        normalized_authored["source_mesh_colliders"],
        normalized_authored["wrapper_colliders"],
        normalized_authored["reports"],
    )
    observation_failures = [
        f"unfiltered:{failure}" for failure in unfiltered_audit["failures"]
    ]
    observation_failures.extend(
        f"authored:{failure}" for failure in authored_audit["failures"]
    )
    if observation_failures:
        return _diagnostic_outcome("OBSERVATION_INCONCLUSIVE", observation_failures)
    return _diagnostic_outcome("FILTER_BEHAVIOR_OBSERVED_DIAGNOSTIC_ONLY", [])
