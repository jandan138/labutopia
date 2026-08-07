"""Pure contract for the isolated OmniPVD effective-offset capability probe.

This diagnostic can establish only that a sealed child captured a uniquely bound
PVD shape for each currently un-authored G0 target. It cannot resolve the G0
gate, issue a clearance certificate, or authorize Phase 3.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any


PLAN_AUTHORITY = "real_pbd_g0_effective_offset_capability_plan_v1"
OBSERVATION_AUTHORITY = "real_pbd_g0_effective_offset_capability_observation_v1"
EVALUATION_AUTHORITY = "real_pbd_g0_effective_offset_capability_evaluation_v1"
TARGET_MANIFEST_AUTHORITY = "real_pbd_g0_pvd_target_manifest_v1"
CLASSIFICATION = "NON_FORMAL_PVD_OFFSET_CAPABILITY_DIAGNOSTIC_ONLY"
PASS = "PVD_OFFSET_CAPABILITY_PASS"
NO_GO = "PVD_OFFSET_CAPABILITY_NO_GO"
PVD_RUNTIME_ARTIFACT_NAMES = (
    "extension_toml",
    "extension_python",
    "converter_python",
    "binding",
    "plugin",
    "runtime_library",
)
_REQUIRED_SHAPE_FLAGS = {"eSIMULATION_SHAPE", "eSCENE_QUERY_SHAPE"}
_AUTHORIZATION = {
    "effective_offsets_resolved": False,
    "g0_go_authorized": False,
    "phase3_authorized": False,
}
_TARGETS = (
    {
        "id": "left_finger",
        "collider_path": "/World/Franka/panda_leftfinger/geometry/panda_leftfinger",
        "actor_name": "/World/Franka/panda_leftfinger",
        "requires_static_actor": False,
    },
    {
        "id": "right_finger",
        "collider_path": "/World/Franka/panda_rightfinger/geometry/panda_rightfinger",
        "actor_name": "/World/Franka/panda_rightfinger",
        "requires_static_actor": False,
    },
    {
        "id": "table",
        "collider_path": "/World/table/surface/mesh",
        "actor_name": "/World/table/surface/mesh",
        "requires_static_actor": True,
    },
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


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _finite_number(value: Any) -> float | None:
    if type(value) not in {int, float}:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def build_plan() -> dict[str, Any]:
    """Return the sole diagnostic-only PVD capture plan."""
    payload = {
        "authority": PLAN_AUTHORITY,
        "schema_version": 1,
        "classification": CLASSIFICATION,
        "targets": [dict(target) for target in _TARGETS],
        "capture": {
            "bootstrap_world_reset_count": 1,
            "explicit_world_step_count": 1,
            "timeline_play_count": 1,
            "timeline_pause_count": 1,
            "maximum_post_disable_finalization_updates": 8,
        },
        "authorization": dict(_AUTHORIZATION),
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


def validate_plan(value: Any) -> dict[str, Any]:
    expected = build_plan()
    if not isinstance(value, Mapping):
        raise ValueError("real_pbd_g0_effective_offset_capability_plan_invalid")
    plan = copy.deepcopy(dict(value))
    digest = plan.pop("sha256", None)
    if (
        set(plan) != set(expected) - {"sha256"}
        or not _is_sha256(digest)
        or canonical_json_sha256(plan) != digest
        or plan.get("authority") != PLAN_AUTHORITY
        or type(plan.get("schema_version")) is not int
        or plan["schema_version"] != 1
        or plan.get("classification") != CLASSIFICATION
        or not isinstance(plan.get("targets"), list)
        or not isinstance(plan.get("capture"), Mapping)
        or not isinstance(plan.get("authorization"), Mapping)
    ):
        raise ValueError("real_pbd_g0_effective_offset_capability_plan_invalid")
    for target in plan["targets"]:
        if (
            not isinstance(target, Mapping)
            or set(target) != {"id", "collider_path", "actor_name", "requires_static_actor"}
            or not isinstance(target.get("id"), str)
            or not isinstance(target.get("collider_path"), str)
            or not target["collider_path"].startswith("/")
            or not isinstance(target.get("actor_name"), str)
            or not target["actor_name"].startswith("/")
            or type(target.get("requires_static_actor")) is not bool
        ):
            raise ValueError("real_pbd_g0_effective_offset_capability_plan_invalid")
    capture = plan["capture"]
    if set(capture) != set(expected["capture"]) or any(
        type(capture.get(name)) is not int for name in expected["capture"]
    ):
        raise ValueError("real_pbd_g0_effective_offset_capability_plan_invalid")
    authorization = plan["authorization"]
    if set(authorization) != set(_AUTHORIZATION) or any(
        type(authorization.get(name)) is not bool for name in _AUTHORIZATION
    ):
        raise ValueError("real_pbd_g0_effective_offset_capability_plan_invalid")
    if plan != {key: item for key, item in expected.items() if key != "sha256"}:
        raise ValueError("real_pbd_g0_effective_offset_capability_plan_invalid")
    return expected


def _artifact_valid(value: Any, *, relative: bool) -> bool:
    if not isinstance(value, Mapping) or set(value) != {"path", "byte_count", "sha256"}:
        return False
    path = value.get("path")
    if not isinstance(path, str) or not path:
        return False
    if relative and (path.startswith("/") or ".." in path.split("/")):
        return False
    if not relative and not path.startswith("/"):
        return False
    return (
        type(value.get("byte_count")) is int
        and value["byte_count"] > 0
        and _is_sha256(value.get("sha256"))
    )


def _runtime_artifacts_valid(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != set(PVD_RUNTIME_ARTIFACT_NAMES):
        return False
    for artifact in value.values():
        if not isinstance(artifact, Mapping) or set(artifact) != {"path", "sha256"}:
            return False
        if not isinstance(artifact.get("path"), str) or not artifact["path"].startswith("/"):
            return False
        if not _is_sha256(artifact.get("sha256")):
            return False
    return True


def _extension_provenance_valid(value: Any) -> bool:
    expected = {"extension_id", "extension_version", "extension_path", "module_origins"}
    if not isinstance(value, Mapping) or set(value) != expected:
        return False
    if (
        not isinstance(value.get("extension_id"), str)
        or not value["extension_id"]
        or not isinstance(value.get("extension_version"), str)
        or not value["extension_version"]
        or not isinstance(value.get("extension_path"), str)
        or not value["extension_path"].startswith("/")
    ):
        return False
    origins = value.get("module_origins")
    return (
        isinstance(origins, Mapping)
        and set(origins) == {"extension_python", "converter_python", "binding"}
        and all(isinstance(path, str) and path.startswith("/") for path in origins.values())
    )


def _recording_checks(value: Any, plan: Mapping[str, Any]) -> tuple[bool, bool]:
    if not isinstance(value, Mapping):
        return False, False
    expected = {
        "capture_authority",
        "pvd_enabled_before_scene",
        "bootstrap_world_reset_count",
        "explicit_world_step_count",
        "timeline_play_count",
        "timeline_pause_count",
        "world_index_before_step",
        "world_index_after_step",
        "pvd_enabled_after_capture",
        "pvd_is_recording_after_capture",
        "post_disable_finalization_updates",
        "operation_counts",
        "timeline_event_counts",
        "finalized_ovd",
        "conversion_artifacts",
    }
    if set(value) != expected:
        return False, False
    capture = plan["capture"]
    numeric_fields = (
        "bootstrap_world_reset_count",
        "explicit_world_step_count",
        "timeline_play_count",
        "timeline_pause_count",
        "world_index_before_step",
        "world_index_after_step",
        "post_disable_finalization_updates",
    )
    if any(type(value.get(name)) is not int for name in numeric_fields):
        return False, False
    operation_counts = value.get("operation_counts")
    timeline_counts = value.get("timeline_event_counts")
    expected_operations = {
        "world_reset": 1,
        "world_step": 1,
        "world_play": 1,
        "world_pause": 1,
        "app_update_finalization": value["post_disable_finalization_updates"],
    }
    operation_types_valid = isinstance(operation_counts, Mapping) and set(operation_counts) == set(
        expected_operations
    ) and all(type(operation_counts.get(name)) is int for name in expected_operations)
    timeline_types_valid = isinstance(timeline_counts, Mapping) and set(timeline_counts) == {
        "timeline_play",
        "timeline_pause",
        "timeline_stop",
    } and all(type(timeline_counts.get(name)) is int for name in timeline_counts)
    lifecycle_valid = (
        value["capture_authority"] == "instrumented_world_and_timeline_v1"
        and value["pvd_enabled_before_scene"] is True
        and value["bootstrap_world_reset_count"] == capture["bootstrap_world_reset_count"]
        and value["explicit_world_step_count"] == capture["explicit_world_step_count"]
        and value["timeline_play_count"] == capture["timeline_play_count"]
        and value["timeline_pause_count"] == capture["timeline_pause_count"]
        and value["world_index_before_step"] >= 0
        and value["world_index_after_step"] == value["world_index_before_step"] + 1
        and value["pvd_enabled_after_capture"] is False
        and value["pvd_is_recording_after_capture"] is False
        and 0 <= value["post_disable_finalization_updates"]
        <= capture["maximum_post_disable_finalization_updates"]
        and operation_types_valid
        and dict(operation_counts) == expected_operations
        and timeline_types_valid
        and timeline_counts["timeline_play"] == 1
        and timeline_counts["timeline_pause"] == 1
        and timeline_counts["timeline_stop"] == 0
    )
    conversion = value["conversion_artifacts"]
    artifacts_valid = (
        _artifact_valid(value["finalized_ovd"], relative=True)
        and value["finalized_ovd"].get("path", "").startswith("pvd-recording/")
        and isinstance(conversion, Sequence)
        and not isinstance(conversion, (str, bytes, bytearray))
        and len(conversion) == 3
        and all(_artifact_valid(item, relative=True) for item in conversion)
        and {item["path"] for item in conversion}
        == {
            "pvd-converted/stage.usda",
            "pvd-converted/scene.usda",
            "pvd-converted/shared.usda",
        }
    )
    return lifecycle_valid, artifacts_valid


def _target_manifest_checks(
    value: Any, plan: Mapping[str, Any]
) -> tuple[bool, bool, dict[str, Any] | None]:
    if not isinstance(value, Mapping):
        return False, False, None
    manifest = copy.deepcopy(dict(value))
    digest = manifest.pop("sha256", None)
    if (
        set(manifest) != {"authority", "targets"}
        or manifest.get("authority") != TARGET_MANIFEST_AUTHORITY
        or not _is_sha256(digest)
        or canonical_json_sha256(manifest) != digest
        or not isinstance(manifest.get("targets"), list)
    ):
        return False, False, None
    expected_targets = {target["id"]: target for target in plan["targets"]}
    seen = set()
    all_unauthored = True
    normalized = {}
    fields = {
        "id",
        "collider_path",
        "actor_name",
        "source_owner_path",
        "source_enabled_collider_paths",
        "source_shape_count",
        "source_prim_type",
        "contact_offset_authored",
        "rest_offset_authored",
    }
    for target in manifest["targets"]:
        if not isinstance(target, Mapping) or set(target) != fields:
            return False, False, None
        identifier = target.get("id")
        expected = expected_targets.get(identifier)
        if not isinstance(identifier, str) or identifier in seen or expected is None:
            return False, False, None
        seen.add(identifier)
        if (
            target.get("collider_path") != expected["collider_path"]
            or target.get("actor_name") != expected["actor_name"]
            or target.get("source_owner_path") != expected["actor_name"]
            or target.get("source_enabled_collider_paths") != [expected["collider_path"]]
            or type(target.get("source_shape_count")) is not int
            or target["source_shape_count"] != 1
            or not isinstance(target.get("source_prim_type"), str)
            or not target["source_prim_type"]
            or type(target.get("contact_offset_authored")) is not bool
            or type(target.get("rest_offset_authored")) is not bool
        ):
            return False, False, None
        all_unauthored = all_unauthored and not target["contact_offset_authored"] and not target[
            "rest_offset_authored"
        ]
        normalized[identifier] = dict(target)
    if seen != set(expected_targets) or len(manifest["targets"]) != len(expected_targets):
        return False, False, None
    return True, all_unauthored, {**manifest, "sha256": digest, "by_id": normalized}


def _pvd_scene_checks(value: Any) -> tuple[bool, bool, dict[str, Any] | None]:
    expected = {
        "pvd_scene_path",
        "pvd_scene_class",
        "sample_time_code",
        "pvd_length_units_per_meter",
        "source_stage_meters_per_unit",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        return False, False, None
    scale = _finite_number(value.get("pvd_length_units_per_meter"))
    meters = _finite_number(value.get("source_stage_meters_per_unit"))
    schema_valid = (
        isinstance(value.get("pvd_scene_path"), str)
        and value["pvd_scene_path"].startswith("/scenes/")
        and value.get("pvd_scene_class") == "PxScene"
        and type(value.get("sample_time_code")) is int
        and value["sample_time_code"] == 0
        and scale is not None
        and scale > 0.0
        and meters is not None
        and meters > 0.0
    )
    scale_valid = schema_valid and math.isclose(
        scale * meters, 1.0, rel_tol=1.0e-6, abs_tol=1.0e-8
    )
    return schema_valid, scale_valid, dict(value) if schema_valid else None


def _stage_immutability_valid(value: Any) -> bool:
    expected = {
        "root_layer_sha256_before",
        "root_layer_sha256_after",
        "session_layer_sha256_before",
        "session_layer_sha256_after",
        "collision_inventory_sha256_before",
        "collision_inventory_sha256_after",
        "unchanged",
    }
    return (
        isinstance(value, Mapping)
        and set(value) == expected
        and all(_is_sha256(value[name]) for name in expected if name != "unchanged")
        and value["unchanged"] is True
        and value["root_layer_sha256_before"] == value["root_layer_sha256_after"]
        and value["session_layer_sha256_before"] == value["session_layer_sha256_after"]
        and value["collision_inventory_sha256_before"]
        == value["collision_inventory_sha256_after"]
    )


def _target_checks(
    value: Any,
    plan: Mapping[str, Any],
    *,
    target_manifest: Mapping[str, Any] | None,
    pvd_scene: Mapping[str, Any] | None,
) -> tuple[bool, bool, bool, bool]:
    if (
        target_manifest is None
        or pvd_scene is None
        or not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
    ):
        return False, False, False, False
    expected_targets = {target["id"]: target for target in plan["targets"]}
    manifest_targets = target_manifest["by_id"]
    seen_ids: set[str] = set()
    seen_actor_paths: set[str] = set()
    seen_shape_paths: set[str] = set()
    mapping_valid = True
    offsets_valid = True
    shape_valid = True
    table_static = True
    fields = {
        "id",
        "collider_path",
        "actor_name",
        "actor_type",
        "pvd_actor_class",
        "pvd_scene_path",
        "pvd_actor_path",
        "pvd_shape_path",
        "sample_time_code",
        "source_target_manifest_sha256",
        "source_owner_path",
        "source_enabled_collider_paths",
        "source_shape_count",
        "pvd_actor_shape_count",
        "pvd_geometry_class",
        "raw_contact_offset_pvd",
        "raw_rest_offset_pvd",
        "pvd_length_units_per_meter",
        "contact_offset_m",
        "rest_offset_m",
        "shape_flags",
    }
    for record in value:
        if not isinstance(record, Mapping) or set(record) != fields:
            mapping_valid = offsets_valid = shape_valid = table_static = False
            continue
        identifier = record.get("id")
        target = expected_targets.get(identifier)
        manifest_target = manifest_targets.get(identifier)
        if (
            not isinstance(identifier, str)
            or identifier in seen_ids
            or target is None
            or manifest_target is None
        ):
            mapping_valid = False
            continue
        seen_ids.add(identifier)
        actor_path = record.get("pvd_actor_path")
        shape_path = record.get("pvd_shape_path")
        if (
            record.get("collider_path") != target["collider_path"]
            or record.get("actor_name") != target["actor_name"]
            or record.get("pvd_scene_path") != pvd_scene["pvd_scene_path"]
            or record.get("source_target_manifest_sha256") != target_manifest["sha256"]
            or record.get("source_owner_path") != manifest_target["source_owner_path"]
            or record.get("source_enabled_collider_paths")
            != manifest_target["source_enabled_collider_paths"]
            or type(record.get("source_shape_count")) is not int
            or record["source_shape_count"] != manifest_target["source_shape_count"]
            or type(record.get("pvd_actor_shape_count")) is not int
            or record["pvd_actor_shape_count"] != 1
            or not isinstance(actor_path, str)
            or not actor_path.startswith(f"{pvd_scene['pvd_scene_path']}/")
            or not isinstance(shape_path, str)
            or not shape_path.startswith(f"{actor_path}/")
            or actor_path in seen_actor_paths
            or shape_path in seen_shape_paths
        ):
            mapping_valid = False
        seen_actor_paths.add(actor_path) if isinstance(actor_path, str) else None
        seen_shape_paths.add(shape_path) if isinstance(shape_path, str) else None
        raw_contact = _finite_number(record.get("raw_contact_offset_pvd"))
        raw_rest = _finite_number(record.get("raw_rest_offset_pvd"))
        scale = _finite_number(record.get("pvd_length_units_per_meter"))
        contact = _finite_number(record.get("contact_offset_m"))
        rest = _finite_number(record.get("rest_offset_m"))
        if (
            raw_contact is None
            or raw_rest is None
            or scale is None
            or scale <= 0.0
            or contact is None
            or rest is None
            or raw_contact < 0.0
            or raw_rest > raw_contact
            or contact < 0.0
            or rest > contact
            or not math.isclose(scale, float(pvd_scene["pvd_length_units_per_meter"]), rel_tol=1.0e-6, abs_tol=1.0e-8)
            or not math.isclose(contact, raw_contact / scale, rel_tol=1.0e-6, abs_tol=1.0e-8)
            or not math.isclose(rest, raw_rest / scale, rel_tol=1.0e-6, abs_tol=1.0e-8)
        ):
            offsets_valid = False
        flags = record.get("shape_flags")
        if (
            type(record.get("sample_time_code")) is not int
            or record["sample_time_code"] != 0
            or not isinstance(record.get("pvd_actor_class"), str)
            or not record["pvd_actor_class"]
            or not isinstance(record.get("pvd_geometry_class"), str)
            or not record["pvd_geometry_class"].startswith("PxGeom")
            or not isinstance(flags, Sequence)
            or isinstance(flags, (str, bytes, bytearray))
            or not _REQUIRED_SHAPE_FLAGS <= set(flags)
        ):
            shape_valid = False
        if target["requires_static_actor"] and record.get("actor_type") != "eRIGID_STATIC":
            table_static = False
    return (
        mapping_valid and seen_ids == set(expected_targets) and len(value) == len(expected_targets),
        offsets_valid,
        shape_valid,
        table_static,
    )


def _validated_observation(value: Any, plan: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("real_pbd_g0_effective_offset_capability_observation_invalid")
    observation = copy.deepcopy(dict(value))
    expected = {
        "authority",
        "schema_version",
        "classification",
        "plan_sha256",
        "authorization",
        "pvd_runtime_artifacts",
        "pvd_extension_provenance",
        "recording",
        "pvd_scene",
        "target_manifest",
        "stage_immutability",
        "target_offsets",
        "sha256",
    }
    digest = observation.pop("sha256", None)
    if (
        set(observation) != expected - {"sha256"}
        or observation.get("authority") != OBSERVATION_AUTHORITY
        or type(observation.get("schema_version")) is not int
        or observation["schema_version"] != 1
        or observation.get("classification") != CLASSIFICATION
        or observation.get("plan_sha256") != plan["sha256"]
        or not _is_sha256(digest)
        or canonical_json_sha256(observation) != digest
    ):
        raise ValueError("real_pbd_g0_effective_offset_capability_observation_invalid")
    return {**observation, "sha256": digest}


def _diagnostic_authorization_valid(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == set(_AUTHORIZATION)
        and all(type(value.get(name)) is bool for name in _AUTHORIZATION)
        and dict(value) == _AUTHORIZATION
    )


def evaluate_observation(value: Any, *, plan: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed unless the diagnostic capture is complete and internally bound."""
    expected_plan = validate_plan(plan)
    observation = _validated_observation(value, expected_plan)
    lifecycle_valid, recording_artifacts_valid = _recording_checks(
        observation["recording"], expected_plan
    )
    manifest_valid, unauthored, target_manifest = _target_manifest_checks(
        observation["target_manifest"], expected_plan
    )
    scene_schema_valid, scale_valid, pvd_scene = _pvd_scene_checks(observation["pvd_scene"])
    mapping_valid, offsets_valid, shape_valid, table_static = _target_checks(
        observation["target_offsets"],
        expected_plan,
        target_manifest=target_manifest,
        pvd_scene=pvd_scene,
    )
    capture_checks = {
        "diagnostic_only_authorization": _diagnostic_authorization_valid(
            observation["authorization"]
        ),
        "pvd_runtime_artifacts_bound": _runtime_artifacts_valid(
            observation["pvd_runtime_artifacts"]
        ),
        "pvd_extension_provenance_bound": _extension_provenance_valid(
            observation["pvd_extension_provenance"]
        ),
        "exact_one_step_pvd_capture": lifecycle_valid,
        "recording_artifacts_sealed": recording_artifacts_valid,
        "pvd_scene_time_zero_complete": scene_schema_valid,
        "pvd_unit_scale_bound": scale_valid,
        "stage_input_unchanged": _stage_immutability_valid(observation["stage_immutability"]),
        "target_manifest_bound": manifest_valid,
        "all_targets_unauthored": unauthored,
        "target_source_to_pvd_cardinality_bound": mapping_valid,
        "finite_effective_offsets": offsets_valid,
        "time_zero_shape_records_complete": shape_valid,
        "table_actor_is_static": table_static,
    }
    # This first lane preserves raw capture evidence only. A future independent
    # sealed verifier must reparse the converted PVD closure before capability
    # evidence can ever become promotable.
    checks = {
        **capture_checks,
        "capture_diagnostic_complete": all(capture_checks.values()),
        "independent_verifier_bound": False,
    }
    payload = {
        "authority": EVALUATION_AUTHORITY,
        "classification": CLASSIFICATION,
        "decision": PASS if all(checks.values()) else NO_GO,
        "checks": checks,
        "authorization": dict(_AUTHORIZATION),
        "plan_sha256": expected_plan["sha256"],
        "observation_sha256": observation["sha256"],
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}
