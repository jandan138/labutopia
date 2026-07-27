"""Fail-closed classification for non-formal direct PhysX contact observations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


_SENSOR_NAMES = ("left", "right", "hand")


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    )


def _sensor_crosscheck(sensor_status: Any) -> tuple[dict[str, Any], list[str]]:
    if sensor_status is None:
        return (
            {
                "provided": False,
                "roles": {
                    name: {"available": False, "observed_source_pair": None}
                    for name in _SENSOR_NAMES
                },
                "unavailable": list(_SENSOR_NAMES),
            },
            [],
        )
    if not isinstance(sensor_status, Mapping) or set(sensor_status) != set(_SENSOR_NAMES):
        return {}, ["sensor_crosscheck_invalid"]

    roles: dict[str, dict[str, bool | None]] = {}
    unavailable: list[str] = []
    for name in _SENSOR_NAMES:
        value = sensor_status[name]
        if not isinstance(value, Mapping) or type(value.get("available")) is not bool:
            return {}, [f"sensor_crosscheck_invalid:{name}"]
        available = value["available"]
        observed = value.get("observed_source_pair")
        if available:
            if type(observed) is not bool:
                return {}, [f"sensor_crosscheck_invalid:{name}"]
        elif observed is not None:
            return {}, [f"sensor_crosscheck_invalid:{name}"]
        roles[name] = {
            "available": available,
            "observed_source_pair": observed,
        }
        if not available:
            unavailable.append(name)
    return (
        {
            "provided": True,
            "roles": roles,
            "unavailable": sorted(unavailable),
        },
        [],
    )


def _result(
    decision: str,
    *,
    left: bool,
    right: bool,
    hand: bool,
    sensor_crosscheck: Mapping[str, Any],
    failures: Sequence[str],
) -> dict[str, Any]:
    return {
        "decision": decision,
        "direct_contact": {"left": left, "right": right, "hand": hand},
        "sensor_crosscheck": dict(sensor_crosscheck),
        "failures": list(failures),
    }


def _contact_identities(value: Any) -> tuple[dict[str, set[str]], dict[str, str]] | None:
    if not isinstance(value, Mapping):
        return None
    names = (
        "source_colliders",
        "left_colliders",
        "right_colliders",
        "hand_colliders",
        "support_colliders",
        "other_colliders",
    )
    groups: dict[str, set[str]] = {}
    known: set[str] = set()
    for name in names:
        paths = value.get(name)
        if not _sequence(paths) or any(not isinstance(path, str) or not path for path in paths):
            return None
        path_set = set(paths)
        if len(path_set) != len(paths) or known.intersection(path_set):
            return None
        if name in {"source_colliders", "left_colliders", "right_colliders"} and not path_set:
            return None
        groups[name] = path_set
        known.update(path_set)
    owners = value.get("collider_owners")
    if (
        not isinstance(owners, Mapping)
        or set(owners) != known
        or any(not isinstance(owner, str) or not owner for owner in owners.values())
    ):
        return None
    return groups, dict(owners)


def _canonical_pair_paths(value: Any) -> tuple[tuple[str, int], tuple[str, int]] | None:
    if not _sequence(value) or len(value) != 2:
        return None
    endpoints = []
    for endpoint in value:
        if not isinstance(endpoint, Mapping):
            return None
        path = endpoint.get("collider_path")
        prototype = endpoint.get("proto_index")
        if (
            not isinstance(path, str)
            or not path
            or type(prototype) is not int
            or prototype < 0
        ):
            return None
        endpoints.append((path, prototype))
    if endpoints[0][0] == endpoints[1][0]:
        return None
    return tuple(sorted(endpoints))


def _classification(
    pair: tuple[tuple[str, int], tuple[str, int]],
    *,
    groups: Mapping[str, set[str]],
) -> str:
    source = groups["source_colliders"]
    pair_set = {path for path, _ in pair}
    if pair_set.intersection(source):
        other = next(iter(pair_set - source), None)
        if other in groups["left_colliders"]:
            return "LEFT_SOURCE"
        if other in groups["right_colliders"]:
            return "RIGHT_SOURCE"
        if other in groups["hand_colliders"]:
            return "HAND_SOURCE"
        if other in groups["support_colliders"]:
            return "SOURCE_SUPPORT"
        return "SOURCE_OTHER"
    robot = (
        groups["left_colliders"]
        | groups["right_colliders"]
        | groups["hand_colliders"]
    )
    if pair_set.intersection(robot) and pair_set - robot:
        return "ROBOT_ENVIRONMENT"
    return "OTHER"


def _header_matches_pair(
    header: Any,
    *,
    pair: tuple[tuple[str, int], tuple[str, int]],
    owners: Mapping[str, str],
) -> str | None:
    if not isinstance(header, Mapping):
        return "fragment_identity_invalid"
    collider0 = header.get("collider0")
    collider1 = header.get("collider1")
    actor0 = header.get("actor0")
    actor1 = header.get("actor1")
    prototype0 = header.get("proto_index0")
    prototype1 = header.get("proto_index1")
    if (
        not isinstance(collider0, str)
        or not isinstance(collider1, str)
        or collider0 not in owners
        or collider1 not in owners
        or collider0 == collider1
    ):
        return "fragment_identity_invalid"
    if (
        type(prototype0) is not int
        or type(prototype1) is not int
        or prototype0 < 0
        or prototype1 < 0
    ):
        return "fragment_prototype_mismatch"
    header_pair = tuple(sorted(((collider0, prototype0), (collider1, prototype1))))
    if header_pair != pair:
        header_paths = tuple(sorted((collider0, collider1)))
        pair_paths = tuple(sorted(path for path, _ in pair))
        return (
            "fragment_prototype_mismatch"
            if header_paths == pair_paths
            else "fragment_identity_invalid"
        )
    if actor0 != owners[collider0] or actor1 != owners[collider1]:
        return "fragment_actor_owner_mismatch"
    return None


def _sample_from_full_report(
    report: Any,
    *,
    identities: Any,
) -> tuple[dict[str, Any] | None, list[str]]:
    resolved = _contact_identities(identities)
    if resolved is None:
        return None, ["direct_contact_identities_invalid"]
    groups, owners = resolved
    if not isinstance(report, Mapping):
        return None, ["full_contact_report_invalid"]
    physics_index = report.get("physics_index")
    occurrences = report.get("occurrences")
    if (
        report.get("authority") != "full_contact_report_step_v1"
        or report.get("range_partition_valid") is not True
        or type(physics_index) is not int
        or physics_index < 0
        or not _sequence(occurrences)
    ):
        return None, ["full_contact_report_invalid"]
    pairs = []
    failures: list[str] = []
    for occurrence in occurrences:
        if not isinstance(occurrence, Mapping):
            failures.append("full_contact_occurrence_invalid")
            continue
        pair = _canonical_pair_paths(occurrence.get("canonical_pair"))
        current = occurrence.get("current")
        transient = occurrence.get("transient")
        headers = occurrence.get("headers")
        points = occurrence.get("contact_data")
        fragments = occurrence.get("fragments")
        if (
            pair is None
            or pair[0][0] not in owners
            or pair[1][0] not in owners
            or type(current) is not bool
            or type(transient) is not bool
            or not _sequence(headers)
            or not _sequence(points)
            or not _sequence(fragments)
            or not fragments
        ):
            failures.append("full_contact_occurrence_invalid")
            continue
        for header in headers:
            failure = _header_matches_pair(header, pair=pair, owners=owners)
            if failure is not None:
                failures.append(failure)
        for fragment in fragments:
            if not isinstance(fragment, Mapping):
                failures.append("fragment_identity_invalid")
                continue
            failure = _header_matches_pair(
                fragment.get("header"), pair=pair, owners=owners
            )
            if failure is not None:
                failures.append(failure)
        pairs.append(
            {
                "classification": _classification(pair, groups=groups),
                "current": current,
                "transient": transient,
                "headers": list(headers),
                "points": list(points),
            }
        )
    if failures:
        return None, sorted(set(failures))
    return {"physics_index": physics_index, "pairs": pairs}, []


def evaluate_full_report_bilateral_contact(
    report: Any,
    *,
    identities: Any,
    sensor_status: Any = None,
) -> dict[str, Any]:
    """Classify a validated immediate-report occurrence buffer.

    Every header and fragment must bind its collider pair to the sealed owner
    map before the summary is eligible for a non-formal observation.
    """

    sample, failures = _sample_from_full_report(report, identities=identities)
    sensor_crosscheck, sensor_failures = _sensor_crosscheck(sensor_status)
    if failures or sensor_failures:
        return _result(
            "AUDIT_NO_GO",
            left=False,
            right=False,
            hand=False,
            sensor_crosscheck=sensor_crosscheck,
            failures=[*failures, *sensor_failures],
        )
    return evaluate_direct_bilateral_contact(
        sample,
        sensor_status=sensor_status,
    )


def evaluate_direct_bilateral_contact(
    sample: Any,
    *,
    sensor_status: Any = None,
) -> dict[str, Any]:
    """Classify one already-normalized immediate PhysX contact sample.

    This is deliberately not a contact parser. Callers must first validate raw
    report headers, identities, ranges, and finite point data. Invalid or absent
    ContactSensor data remains diagnostic metadata; only a valid sensor-positive
    observation missing from the same direct report is a contradiction.
    """

    empty_crosscheck, sensor_failures = _sensor_crosscheck(sensor_status)
    if sensor_failures:
        return _result(
            "AUDIT_NO_GO",
            left=False,
            right=False,
            hand=False,
            sensor_crosscheck=empty_crosscheck,
            failures=sensor_failures,
        )
    if not isinstance(sample, Mapping):
        return _result(
            "AUDIT_NO_GO",
            left=False,
            right=False,
            hand=False,
            sensor_crosscheck=empty_crosscheck,
            failures=["direct_contact_sample_invalid"],
        )
    physics_index = sample.get("physics_index")
    pairs = sample.get("pairs")
    if type(physics_index) is not int or physics_index < 0 or not _sequence(pairs):
        return _result(
            "AUDIT_NO_GO",
            left=False,
            right=False,
            hand=False,
            sensor_crosscheck=empty_crosscheck,
            failures=["direct_contact_sample_invalid"],
        )

    observed = {"left": False, "right": False, "hand": False}
    invalid: list[str] = []
    unexpected: set[str] = set()
    for pair in pairs:
        if not isinstance(pair, Mapping):
            invalid.append("direct_contact_pair_invalid")
            continue
        classification = pair.get("classification")
        current = pair.get("current")
        transient = pair.get("transient")
        headers = pair.get("headers")
        points = pair.get("points")
        if (
            not isinstance(classification, str)
            or type(current) is not bool
            or type(transient) is not bool
            or not _sequence(headers)
            or not _sequence(points)
            or any(not isinstance(point, Mapping) for point in points)
            or (current and transient)
        ):
            invalid.append("direct_contact_pair_invalid")
            continue
        unexpected_failure = {
            "HAND_SOURCE": "hand_source_contact",
            "SOURCE_OTHER": "unexpected_source_contact",
            "ROBOT_ENVIRONMENT": "robot_environment_contact",
        }.get(classification)
        if unexpected_failure is not None:
            unexpected.add(unexpected_failure)
        if not current:
            continue
        side = {
            "LEFT_SOURCE": "left",
            "RIGHT_SOURCE": "right",
            "HAND_SOURCE": "hand",
        }.get(classification)
        if side is not None:
            if not headers or not points:
                invalid.append(f"{side}_direct_contact_evidence_invalid")
                continue
            observed[side] = True

    if invalid:
        return _result(
            "AUDIT_NO_GO",
            left=observed["left"],
            right=observed["right"],
            hand=observed["hand"],
            sensor_crosscheck=empty_crosscheck,
            failures=sorted(set(invalid)),
        )

    sensor_pairs = {
        "left": observed["left"],
        "right": observed["right"],
        "hand": observed["hand"],
    }
    disagreements = [
        f"sensor_direct_disagreement:{name}"
        for name, role in empty_crosscheck["roles"].items()
        if role["available"] is True
        and role["observed_source_pair"] is True
        and sensor_pairs[name] is not True
    ]
    if disagreements:
        return _result(
            "AUDIT_NO_GO",
            left=observed["left"],
            right=observed["right"],
            hand=observed["hand"],
            sensor_crosscheck=empty_crosscheck,
            failures=disagreements,
        )

    failures = []
    if not observed["left"]:
        failures.append("left_direct_contact_missing")
    if not observed["right"]:
        failures.append("right_direct_contact_missing")
    failures.extend(sorted(unexpected))
    return _result(
        "OBSERVED" if not failures else "PHYSICAL_FAIL",
        left=observed["left"],
        right=observed["right"],
        hand=observed["hand"],
        sensor_crosscheck=empty_crosscheck,
        failures=failures,
    )
