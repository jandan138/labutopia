"""Pure-Python contracts for scoped full-robot collision observations.

The scope payload has exactly eight fields and may additionally carry its
``sha256``. The returned normalized scope always carries that digest, computed
from the payload with canonical JSON. A supplied digest must match.
Declared collider paths, and robot owner paths, are scoped roots: an unlisted
collider at or below one of those paths is classified as unknown rather than
being treated as out of scope.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


_SCOPE_AUTHORITY = "nonformal_v9_full_robot_collision_scope_v1"
_TARGET_NAMES = (
    "beaker1",
    "source_wrapper",
    "table",
    "source_shell",
)
_SCOPE_PAYLOAD_FIELDS = frozenset(
    {
        "authority",
        "robot_root_path",
        "robot_colliders",
        "left_finger_colliders",
        "right_finger_colliders",
        "target_colliders",
        "target_root_paths",
        "collider_owners",
    }
)
_SCOPE_FIELDS = _SCOPE_PAYLOAD_FIELDS | {"sha256"}
_HEADER_FIELDS = frozenset({"actor0", "actor1", "collider0", "collider1"})
_SAMPLE_FIELDS = frozenset({"callback_ordinal", "pick_event", "headers"})
_COVERAGE_FIELDS = frozenset(
    {"before_world_index", "after_world_index", "callback_count"}
)


def canonical_json_sha256(value: Any) -> str:
    """Return the SHA-256 digest of a deterministic JSON representation."""
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("nonformal_v9_collision_json_invalid") from exc
    return hashlib.sha256(encoded).hexdigest()


def _absolute_path(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value.startswith("/")


def _sorted_path_list(value: Any, *, field: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(not _absolute_path(path) for path in value)
        or value != sorted(value)
        or len(value) != len(set(value))
    ):
        raise ValueError(f"nonformal_v9_collision_{field}_invalid")
    return list(value)


def _sha256(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("nonformal_v9_collision_scope_sha256_invalid")
    return value


def _path_is_at_or_below(path: str, root: str) -> bool:
    normalized_root = root.rstrip("/") or "/"
    return (
        normalized_root == "/"
        or path == normalized_root
        or path.startswith(f"{normalized_root}/")
    )


def validate_collision_scope(scope: Any) -> dict[str, Any]:
    """Validate and digest the exact collision-scope schema.

    The accepted input has the payload fields documented at module level, with
    an optional ``sha256`` field. The normalized return value always has the
    digest and uses sorted plain lists and mappings.
    """
    if not isinstance(scope, Mapping):
        raise ValueError("nonformal_v9_collision_scope_invalid")
    raw = dict(scope)
    if frozenset(raw) not in (_SCOPE_PAYLOAD_FIELDS, _SCOPE_FIELDS):
        raise ValueError("nonformal_v9_collision_scope_invalid")
    if raw["authority"] != _SCOPE_AUTHORITY:
        raise ValueError("nonformal_v9_collision_scope_authority_invalid")
    robot_root_path = raw["robot_root_path"]
    if not _absolute_path(robot_root_path):
        raise ValueError("nonformal_v9_collision_robot_root_path_invalid")

    robot_colliders = _sorted_path_list(
        raw["robot_colliders"], field="robot_colliders"
    )
    left_finger_colliders = _sorted_path_list(
        raw["left_finger_colliders"], field="left_finger_colliders"
    )
    right_finger_colliders = _sorted_path_list(
        raw["right_finger_colliders"], field="right_finger_colliders"
    )
    robot_set = set(robot_colliders)
    if not all(
        _path_is_at_or_below(collider, robot_root_path)
        for collider in robot_colliders
    ):
        raise ValueError("nonformal_v9_collision_robot_colliders_root_invalid")
    if not set(left_finger_colliders) <= robot_set:
        raise ValueError("nonformal_v9_collision_left_finger_subset_invalid")
    if not set(right_finger_colliders) <= robot_set:
        raise ValueError("nonformal_v9_collision_right_finger_subset_invalid")

    raw_targets = raw["target_colliders"]
    if not isinstance(raw_targets, Mapping) or set(raw_targets) != set(_TARGET_NAMES):
        raise ValueError("nonformal_v9_collision_target_colliders_invalid")
    raw_target_roots = raw["target_root_paths"]
    if (
        not isinstance(raw_target_roots, Mapping)
        or set(raw_target_roots) != set(_TARGET_NAMES)
        or any(not _absolute_path(raw_target_roots[name]) for name in _TARGET_NAMES)
        or len(set(raw_target_roots.values())) != len(_TARGET_NAMES)
        or any(
            _path_is_at_or_below(raw_target_roots[name], robot_root_path)
            or _path_is_at_or_below(robot_root_path, raw_target_roots[name])
            for name in _TARGET_NAMES
        )
    ):
        raise ValueError("nonformal_v9_collision_target_root_paths_invalid")
    target_root_paths = {
        name: raw_target_roots[name] for name in _TARGET_NAMES
    }
    target_colliders = {
        name: _sorted_path_list(
            raw_targets[name], field=f"target_{name}_colliders"
        )
        for name in _TARGET_NAMES
    }
    if not all(
        _path_is_at_or_below(collider, target_root_paths[name])
        for name in _TARGET_NAMES
        for collider in target_colliders[name]
    ):
        raise ValueError("nonformal_v9_collision_target_colliders_root_invalid")
    all_target_colliders = [
        collider
        for name in _TARGET_NAMES
        for collider in target_colliders[name]
    ]
    if (
        len(all_target_colliders) != len(set(all_target_colliders))
        or robot_set.intersection(all_target_colliders)
    ):
        raise ValueError("nonformal_v9_collision_collider_partition_invalid")

    raw_owners = raw["collider_owners"]
    if not isinstance(raw_owners, Mapping) or set(raw_owners) != robot_set:
        raise ValueError("nonformal_v9_collision_collider_owners_invalid")
    collider_owners = {}
    for collider in robot_colliders:
        owner = raw_owners[collider]
        if not _absolute_path(owner) or not _path_is_at_or_below(owner, robot_root_path):
            raise ValueError("nonformal_v9_collision_collider_owners_invalid")
        collider_owners[collider] = owner

    payload = {
        "authority": _SCOPE_AUTHORITY,
        "robot_root_path": robot_root_path,
        "robot_colliders": robot_colliders,
        "left_finger_colliders": left_finger_colliders,
        "right_finger_colliders": right_finger_colliders,
        "target_colliders": target_colliders,
        "target_root_paths": target_root_paths,
        "collider_owners": collider_owners,
    }
    digest = canonical_json_sha256(payload)
    if "sha256" in raw and _sha256(raw["sha256"]) != digest:
        raise ValueError("nonformal_v9_collision_scope_sha256_mismatch")
    return {**payload, "sha256": digest}


def _validate_header(header: Any) -> dict[str, str]:
    if not isinstance(header, Mapping) or set(header) != _HEADER_FIELDS:
        raise ValueError("nonformal_v9_collision_header_invalid")
    normalized = {field: header[field] for field in sorted(_HEADER_FIELDS)}
    if any(not _absolute_path(path) for path in normalized.values()):
        raise ValueError("nonformal_v9_collision_header_invalid")
    return normalized


def _contact_result(
    classification: str,
    collider0: str,
    collider1: str,
) -> dict[str, Any]:
    return {
        "classification": classification,
        "canonical_collider_pair": sorted((collider0, collider1)),
    }


def classify_scoped_contact(
    header: Any,
    scope: Any,
    *,
    pick_event: Any,
) -> dict[str, Any]:
    """Classify one header from collider paths under a validated scope."""
    normalized_scope = validate_collision_scope(scope)
    normalized_header = _validate_header(header)
    collider0 = normalized_header["collider0"]
    collider1 = normalized_header["collider1"]
    colliders = (collider0, collider1)

    robot_colliders = set(normalized_scope["robot_colliders"])
    target_by_collider = {
        collider: name
        for name, target_colliders in normalized_scope["target_colliders"].items()
        for collider in target_colliders
    }
    known_colliders = robot_colliders | set(target_by_collider)
    scoped_roots = (
        normalized_scope["robot_root_path"],
        *normalized_scope["target_root_paths"].values(),
    )
    if any(
        collider not in known_colliders
        and any(_path_is_at_or_below(collider, root) for root in scoped_roots)
        for collider in colliders
    ):
        return _contact_result("UNKNOWN_SCOPED_CONTACT", collider0, collider1)

    robot_matches = [
        collider for collider in colliders if collider in robot_colliders
    ]
    target_matches = [
        collider for collider in colliders if collider in target_by_collider
    ]
    if len(robot_matches) != 1 or len(target_matches) != 1:
        return _contact_result("OUT_OF_SCOPE", collider0, collider1)

    robot_collider = robot_matches[0]
    target_name = target_by_collider[target_matches[0]]
    robot_actor = (
        normalized_header["actor0"]
        if collider0 == robot_collider
        else normalized_header["actor1"]
    )
    if robot_actor != normalized_scope["collider_owners"][robot_collider]:
        return _contact_result(
            "FORBIDDEN_ACTOR_OWNER_MISMATCH", collider0, collider1
        )
    if target_name != "source_shell":
        return _contact_result(
            f"FORBIDDEN_{target_name.upper()}", collider0, collider1
        )

    finger_colliders = set(normalized_scope["left_finger_colliders"])
    finger_colliders.update(normalized_scope["right_finger_colliders"])
    if (
        robot_collider in finger_colliders
        and type(pick_event) is int
        and pick_event >= 4
    ):
        return _contact_result(
            "ALLOWED_SOURCE_SHELL_FINGER", collider0, collider1
        )
    return _contact_result("FORBIDDEN_SOURCE_SHELL", collider0, collider1)


def evaluate_callback_coverage(records: Any) -> dict[str, Any]:
    """Check that callback blocks cover one positive, consecutive index range."""
    if not isinstance(records, list):
        return {"audit_valid": False, "failures": ["records_invalid"]}
    if not records:
        return {"audit_valid": False, "failures": ["records_empty"]}

    failures: list[str] = []
    previous_after: int | None = None
    for ordinal, record in enumerate(records):
        if not isinstance(record, Mapping) or not _COVERAGE_FIELDS <= set(record):
            failures.append(f"record_{ordinal}_invalid")
            previous_after = None
            continue
        before = record["before_world_index"]
        after = record["after_world_index"]
        callback_count = record["callback_count"]
        if any(
            type(value) is not int or value < 0
            for value in (before, after, callback_count)
        ):
            failures.append(f"record_{ordinal}_invalid")
            previous_after = None
            continue

        delta = after - before
        if delta <= 0:
            failures.append(f"record_{ordinal}_delta_not_positive")
        if callback_count != delta:
            failures.append(f"record_{ordinal}_callback_count_mismatch")
        if previous_after is not None and before != previous_after:
            failures.append(f"record_{ordinal}_not_consecutive")
        previous_after = after

    return {"audit_valid": not failures, "failures": failures}


def evaluate_collision_observations(scope: Any, samples: Any) -> dict[str, Any]:
    """Evaluate ordered callback samples and retain the first invalid contact."""
    normalized_scope = validate_collision_scope(scope)
    if not isinstance(samples, list) or not samples:
        raise ValueError("nonformal_v9_collision_samples_invalid")

    classification_counts: dict[str, int] = {}
    first_forbidden_evidence: dict[str, Any] | None = None
    header_count = 0
    for expected_ordinal, sample in enumerate(samples):
        if not isinstance(sample, Mapping) or not _SAMPLE_FIELDS <= set(sample):
            raise ValueError("nonformal_v9_collision_sample_invalid")
        callback_ordinal = sample["callback_ordinal"]
        if type(callback_ordinal) is not int or callback_ordinal != expected_ordinal:
            raise ValueError("nonformal_v9_collision_callback_ordinal_invalid")
        pick_event = sample["pick_event"]
        if pick_event is not None and (
            type(pick_event) is not int or not 0 <= pick_event <= 6
        ):
            raise ValueError("nonformal_v9_collision_pick_event_invalid")
        headers = sample["headers"]
        if not isinstance(headers, list):
            raise ValueError("nonformal_v9_collision_headers_invalid")

        for header_ordinal, header in enumerate(headers):
            contact = classify_scoped_contact(
                header,
                normalized_scope,
                pick_event=pick_event,
            )
            header_count += 1
            classification = contact["classification"]
            classification_counts[classification] = (
                classification_counts.get(classification, 0) + 1
            )
            if (
                first_forbidden_evidence is None
                and (
                    classification.startswith("FORBIDDEN_")
                    or classification == "UNKNOWN_SCOPED_CONTACT"
                )
            ):
                normalized_header = _validate_header(header)
                first_forbidden_evidence = {
                    "callback_ordinal": callback_ordinal,
                    "header_ordinal": header_ordinal,
                    "pick_event": pick_event,
                    "header": normalized_header,
                    "contact": contact,
                }

    return {
        "audit_valid": first_forbidden_evidence is None,
        "scope_sha256": normalized_scope["sha256"],
        "sample_count": len(samples),
        "header_count": header_count,
        "classification_counts": dict(sorted(classification_counts.items())),
        "first_forbidden_evidence": first_forbidden_evidence,
    }
