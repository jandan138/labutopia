"""Pure contract for the nonauthorizing finite-offset calibration overlay.

This lane proves only composed USD authoring. It cannot resolve native PhysX
effective offsets, a clearance certificate, G0, or Phase 3.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any


PLAN_AUTHORITY = "nonauthorizing_authored_offset_overlay_composition_plan_v1"
OBSERVATION_AUTHORITY = "nonauthorizing_authored_offset_overlay_composition_observation_v1"
EVALUATION_AUTHORITY = "nonauthorizing_authored_offset_overlay_composition_evaluation_v1"
OVERLAY_PROFILE_AUTHORITY = "nonauthorizing_authored_offset_overlay_profile_v1"
OVERLAY_PROFILE_ID = "finite_target_offsets_calibration_v2"
CLASSIFICATION = "NONAUTHORIZING_AUTHORED_OFFSET_CALIBRATION_TREATMENT"
PASS = "USD_AUTHORED_OFFSET_OVERLAY_COMPOSITION_PASS"
NO_GO = "USD_AUTHORED_OFFSET_OVERLAY_COMPOSITION_NO_GO"
AUTHORIZATION = {
    "effective_offsets_resolved": False,
    "clearance_certificate_authorized": False,
    "g0_go_authorized": False,
    "phase3_authorized": False,
}
_TARGETS = (
    {
        "id": "left_finger",
        "collider_path": "/World/Franka/panda_leftfinger/geometry/panda_leftfinger",
        "contact_offset_m": 0.001,
        "rest_offset_m": 0.0,
    },
    {
        "id": "right_finger",
        "collider_path": "/World/Franka/panda_rightfinger/geometry/panda_rightfinger",
        "contact_offset_m": 0.001,
        "rest_offset_m": 0.0,
    },
    {
        "id": "table",
        "collider_path": "/World/table/surface/mesh",
        "contact_offset_m": 0.00164,
        "rest_offset_m": 0.0,
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


def expected_overlay_usda() -> str:
    """Return the immutable, allowlisted calibration overlay bytes as text."""
    return """#usda 1.0
(
    defaultPrim = \"World\"
)

over \"World\"
{
    over \"Franka\"
    {
        over \"panda_leftfinger\"
        {
            over \"geometry\"
            {
                over \"panda_leftfinger\" (
                    prepend apiSchemas = [\"PhysxCollisionAPI\"]
                )
                {
                    float physxCollision:contactOffset = 0.001
                    float physxCollision:restOffset = 0
                }
            }
        }
        over \"panda_rightfinger\"
        {
            over \"geometry\"
            {
                over \"panda_rightfinger\" (
                    prepend apiSchemas = [\"PhysxCollisionAPI\"]
                )
                {
                    float physxCollision:contactOffset = 0.001
                    float physxCollision:restOffset = 0
                }
            }
        }
    }
    over \"table\"
    {
        over \"surface\"
        {
            over \"mesh\" (
                prepend apiSchemas = [\"PhysxCollisionAPI\"]
            )
            {
                float physxCollision:contactOffset = 0.00164
                float physxCollision:restOffset = 0
            }
        }
    }
}
"""


def build_plan() -> dict[str, Any]:
    payload = {
        "authority": PLAN_AUTHORITY,
        "schema_version": 1,
        "classification": CLASSIFICATION,
        "overlay_profile_id": OVERLAY_PROFILE_ID,
        "targets": [dict(target) for target in _TARGETS],
        "runtime_prohibitions": {
            "world_constructed": False,
            "world_reset_count": 0,
            "world_step_count": 0,
            "timeline_play_count": 0,
            "pvd_recording_configured": False,
        },
        "authorization": dict(AUTHORIZATION),
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _absolute_path(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("/")
        and value != "/"
        and not value.endswith("/")
        and "//" not in value
    )


def validate_plan(value: Any) -> dict[str, Any]:
    expected = build_plan()
    if not isinstance(value, Mapping):
        raise ValueError("nonauthorizing_authored_offset_plan_invalid")
    plan = copy.deepcopy(dict(value))
    digest = plan.pop("sha256", None)
    if (
        not _is_sha256(digest)
        or canonical_json_sha256(plan) != digest
        or plan != {key: item for key, item in expected.items() if key != "sha256"}
    ):
        raise ValueError("nonauthorizing_authored_offset_plan_invalid")
    return expected


def _artifact(value: Any) -> dict[str, str] | None:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"path", "sha256"}
        or not _absolute_path(value.get("path"))
        or not _is_sha256(value.get("sha256"))
    ):
        return None
    return {"path": value["path"], "sha256": value["sha256"]}


def _fixture(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping) or set(value) != {
        "asset",
        "robot_asset",
        "overlay_profile",
        "overlay_profile_sha256",
    }:
        return None
    asset = _artifact(value["asset"])
    robot_asset = _artifact(value["robot_asset"])
    profile = value["overlay_profile"]
    if (
        asset is None
        or robot_asset is None
        or not isinstance(profile, Mapping)
        or set(profile) != {"authority", "id", "overlay_stack"}
        or profile.get("authority") != OVERLAY_PROFILE_AUTHORITY
        or profile.get("id") != OVERLAY_PROFILE_ID
        or not isinstance(profile.get("overlay_stack"), list)
        or len(profile["overlay_stack"]) != 2
        or value.get("overlay_profile_sha256") != canonical_json_sha256(profile)
    ):
        return None
    stack = []
    for item, expected_id in zip(
        profile["overlay_stack"],
        (OVERLAY_PROFILE_ID, "hidden_cube_collision_disable"),
        strict=True,
    ):
        artifact = (
            _artifact({"path": item.get("path"), "sha256": item.get("sha256")})
            if isinstance(item, Mapping)
            else None
        )
        if artifact is None or set(item) != {"id", "path", "sha256"} or item.get("id") != expected_id:
            return None
        stack.append({"id": expected_id, **artifact})
    normalized_profile = {
        "authority": OVERLAY_PROFILE_AUTHORITY,
        "id": OVERLAY_PROFILE_ID,
        "overlay_stack": stack,
    }
    return {
        "asset": asset,
        "robot_asset": robot_asset,
        "overlay_profile": normalized_profile,
        "overlay_profile_sha256": canonical_json_sha256(normalized_profile),
    }


def _kit_profile(value: Any) -> dict[str, Any] | None:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"path", "sha256", "pvd_extension_declared"}
        or not _absolute_path(value.get("path"))
        or not _is_sha256(value.get("sha256"))
        or value.get("pvd_extension_declared") is not False
    ):
        return None
    return {
        "path": value["path"],
        "sha256": value["sha256"],
        "pvd_extension_declared": False,
    }


def _closure(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping) or set(value) != {"layers", "sha256"}:
        return None
    layers = value.get("layers")
    if not isinstance(layers, list) or not layers:
        return None
    normalized = []
    for layer in layers:
        if (
            not isinstance(layer, Mapping)
            or set(layer) != {"identifier", "real_path", "sha256"}
            or not isinstance(layer.get("identifier"), str)
            or not layer["identifier"]
            or not _absolute_path(layer.get("real_path"))
            or not _is_sha256(layer.get("sha256"))
        ):
            return None
        normalized.append(
            {
                "identifier": layer["identifier"],
                "real_path": layer["real_path"],
                "sha256": layer["sha256"],
            }
        )
    if (
        normalized != sorted(normalized, key=lambda item: item["real_path"])
        or len({item["real_path"] for item in normalized}) != len(normalized)
        or value.get("sha256") != canonical_json_sha256({"layers": normalized})
    ):
        return None
    return {"layers": normalized, "sha256": value["sha256"]}


def _closure_contains(closure: Mapping[str, Any] | None, artifact: Mapping[str, Any]) -> bool:
    if closure is None:
        return False
    return any(
        layer["real_path"] == artifact["path"] and layer["sha256"] == artifact["sha256"]
        for layer in closure["layers"]
    )


def _resolved_dependency_closure(
    value: Any, *, expected_entries: list[dict[str, str]]
) -> dict[str, Any] | None:
    if not isinstance(value, Mapping) or set(value) != {
        "entries",
        "files",
        "runtime_mdl_files",
        "runtime_mdl_builtin_modules",
        "unresolved",
        "texture_unresolved",
        "sha256",
    }:
        return None
    entries = value.get("entries")
    files = value.get("files")
    runtime_mdl_files = value.get("runtime_mdl_files")
    runtime_mdl_builtin_modules = value.get("runtime_mdl_builtin_modules")
    unresolved = value.get("unresolved")
    texture_unresolved = value.get("texture_unresolved")
    if (
        entries != expected_entries
        or not isinstance(files, list)
        or not isinstance(runtime_mdl_files, list)
        or not isinstance(runtime_mdl_builtin_modules, list)
        or not isinstance(unresolved, list)
        or not isinstance(texture_unresolved, list)
        or unresolved
        or texture_unresolved
        or not _is_sha256(value.get("sha256"))
    ):
        return None
    normalized_files = []
    for record in files:
        if (
            not isinstance(record, Mapping)
            or set(record) != {"path", "byte_count", "sha256"}
            or not _absolute_path(record.get("path"))
            or type(record.get("byte_count")) is not int
            or record["byte_count"] < 0
            or not _is_sha256(record.get("sha256"))
        ):
            return None
        normalized_files.append(dict(record))
    normalized_mdl_files = []
    for record in runtime_mdl_files:
        if (
            not isinstance(record, Mapping)
            or set(record) != {"purpose", "path", "byte_count", "sha256"}
            or record.get("purpose") not in {"kit_mdl_material_root", "kit_mdl_material_dependency"}
            or not _absolute_path(record.get("path"))
            or type(record.get("byte_count")) is not int
            or record["byte_count"] < 0
            or not _is_sha256(record.get("sha256"))
        ):
            return None
        normalized_mdl_files.append(dict(record))
    if (
        normalized_files != sorted(normalized_files, key=lambda item: item["path"])
        or len({record["path"] for record in normalized_files}) != len(normalized_files)
        or normalized_mdl_files != sorted(normalized_mdl_files, key=lambda item: item["path"])
        or len({record["path"] for record in normalized_mdl_files}) != len(normalized_mdl_files)
        or runtime_mdl_builtin_modules != sorted(set(runtime_mdl_builtin_modules))
        or any(not isinstance(item, str) or not item.startswith("::") for item in runtime_mdl_builtin_modules)
        or any(
            not any(
                file["path"] == entry["path"] and file["sha256"] == entry["sha256"]
                for file in normalized_files
            )
            for entry in expected_entries
        )
        or value["sha256"]
        != canonical_json_sha256(
            {
                "entries": expected_entries,
                "files": normalized_files,
                "runtime_mdl_files": normalized_mdl_files,
                "runtime_mdl_builtin_modules": runtime_mdl_builtin_modules,
                "unresolved": [],
                "texture_unresolved": [],
            }
        )
    ):
        return None
    return {
        "entries": expected_entries,
        "files": normalized_files,
        "runtime_mdl_files": normalized_mdl_files,
        "runtime_mdl_builtin_modules": runtime_mdl_builtin_modules,
        "texture_unresolved": [],
        "unresolved": [],
        "sha256": value["sha256"],
    }


def _timeline_receipt(value: Any) -> dict[str, Any] | None:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"is_playing", "time_s"}
        or type(value.get("is_playing")) is not bool
        or _finite_number(value.get("time_s")) is None
    ):
        return None
    return {"is_playing": value["is_playing"], "time_s": float(value["time_s"])}


def _validated_observation(value: Any, plan: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "authority",
        "schema_version",
        "classification",
        "plan_sha256",
        "authorization",
        "fixture",
        "kit_profile",
        "input_usd_dependency_closures",
        "resolved_usd_dependency_closures",
        "stage",
        "runtime_scope",
        "overlay_layer",
        "targets",
        "sha256",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("nonauthorizing_authored_offset_observation_invalid")
    observation = copy.deepcopy(dict(value))
    digest = observation.pop("sha256")
    if (
        observation.get("authority") != OBSERVATION_AUTHORITY
        or observation.get("schema_version") != 1
        or observation.get("classification") != CLASSIFICATION
        or observation.get("plan_sha256") != plan["sha256"]
        or not _is_sha256(digest)
        or canonical_json_sha256(observation) != digest
    ):
        raise ValueError("nonauthorizing_authored_offset_observation_invalid")
    return {**observation, "sha256": digest}


def _offset_checks(value: Any, *, expected_value: float, overlay_path: str) -> tuple[bool, bool, bool]:
    if not isinstance(value, Mapping) or set(value) != {
        "authored",
        "composed_value_m",
        "property_stack_layer_paths",
        "strongest_property_stack_default_m",
    }:
        return False, False, False
    stack = value.get("property_stack_layer_paths")
    composed = _finite_number(value.get("composed_value_m"))
    strongest = _finite_number(value.get("strongest_property_stack_default_m"))
    finite = composed is not None and strongest is not None
    provenance = (
        isinstance(stack, list)
        and bool(stack)
        and all(isinstance(path, str) and path for path in stack)
        and stack[0] == overlay_path
    )
    value_matches = (
        value.get("authored") is True
        and finite
        and math.isclose(float(composed), expected_value, rel_tol=0.0, abs_tol=1.0e-9)
        and math.isclose(float(strongest), expected_value, rel_tol=0.0, abs_tol=1.0e-9)
    )
    return finite, provenance, value_matches


def evaluate_observation(
    value: Any,
    *,
    plan: Mapping[str, Any],
    fixture: Mapping[str, Any],
    kit_profile: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate static USD composition without assigning effective-offset authority."""
    expected_plan = validate_plan(plan)
    expected_fixture = _fixture(fixture)
    expected_kit_profile = _kit_profile(kit_profile)
    if expected_fixture is None or expected_kit_profile is None:
        raise ValueError("nonauthorizing_authored_offset_expected_binding_invalid")
    observation = _validated_observation(value, expected_plan)
    closure_record = observation.get("input_usd_dependency_closures")
    before = closure_record.get("before") if isinstance(closure_record, Mapping) else None
    after = closure_record.get("after") if isinstance(closure_record, Mapping) else None
    closure_before = _closure(before)
    closure_after = _closure(after)
    dependency_record = observation.get("resolved_usd_dependency_closures")
    hidden_cube = next(
        item
        for item in expected_fixture["overlay_profile"]["overlay_stack"]
        if item["id"] == "hidden_cube_collision_disable"
    )
    expected_dependency_stacks = {
        "cube_only_baseline_v1": [hidden_cube],
        "finite_target_offsets_calibration_v2": expected_fixture["overlay_profile"]["overlay_stack"],
    }
    resolved_dependency_closure_complete = (
        isinstance(dependency_record, Mapping)
        and set(dependency_record) == set(expected_dependency_stacks)
    )
    if isinstance(dependency_record, Mapping):
        for profile_id, stack in expected_dependency_stacks.items():
            expected_dependency_entries = [
                {"id": "fixture_asset", **expected_fixture["asset"]},
                {"id": "robot_asset", **expected_fixture["robot_asset"]},
                *(
                    {"id": item["id"], "path": item["path"], "sha256": item["sha256"]}
                    for item in stack
                ),
            ]
            profile_record = dependency_record.get(profile_id)
            dependency_before = _resolved_dependency_closure(
                profile_record.get("before") if isinstance(profile_record, Mapping) else None,
                expected_entries=expected_dependency_entries,
            )
            dependency_after = _resolved_dependency_closure(
                profile_record.get("after") if isinstance(profile_record, Mapping) else None,
                expected_entries=expected_dependency_entries,
            )
            resolved_dependency_closure_complete = (
                resolved_dependency_closure_complete
                and dependency_before is not None
                and dependency_before == dependency_after
            )
    stage = observation.get("stage")
    scope = observation.get("runtime_scope")
    overlay = observation.get("overlay_layer")
    target_records = observation.get("targets")
    calibration = next(
        item
        for item in expected_fixture["overlay_profile"]["overlay_stack"]
        if item["id"] == OVERLAY_PROFILE_ID
    )
    expected_sublayers = [
        item["path"] for item in expected_fixture["overlay_profile"]["overlay_stack"]
    ]
    fixture_bound = observation.get("fixture") == expected_fixture
    kit_profile_bound = observation.get("kit_profile") == expected_kit_profile
    pvd_not_declared = (
        kit_profile_bound and expected_kit_profile["pvd_extension_declared"] is False
    )
    closure_stable = closure_before is not None and closure_before == closure_after
    declared_direct_inputs_bound = closure_before is not None and all(
        _closure_contains(closure_before, artifact)
        for artifact in (
            expected_fixture["asset"],
            expected_fixture["robot_asset"],
            *expected_fixture["overlay_profile"]["overlay_stack"],
        )
    )
    stage_composition_stable = (
        isinstance(stage, Mapping)
        and set(stage)
        == {
            "meters_per_unit",
            "up_axis",
            "session_sublayer_paths",
            "robot_reference_ready_before_treatment",
            "cube_collision_disabled",
            "root_layer_sha256_before",
            "root_layer_sha256_after",
            "session_layer_sha256_before",
            "session_layer_sha256_after",
            "composition_unchanged",
        }
        and _finite_number(stage.get("meters_per_unit")) == 1.0
        and stage.get("up_axis") == "Z"
        and stage.get("session_sublayer_paths") == expected_sublayers
        and stage.get("robot_reference_ready_before_treatment") is True
        and stage.get("cube_collision_disabled") is True
        and all(
            _is_sha256(stage.get(name))
            for name in (
                "root_layer_sha256_before",
                "root_layer_sha256_after",
                "session_layer_sha256_before",
                "session_layer_sha256_after",
            )
        )
        and stage.get("root_layer_sha256_before") == stage.get("root_layer_sha256_after")
        and stage.get("session_layer_sha256_before") == stage.get("session_layer_sha256_after")
        and stage.get("composition_unchanged") is True
    )
    no_world_or_timeline_advancement = (
        isinstance(scope, Mapping)
        and set(scope)
        == {
            "world_constructed",
            "world_reset_count",
            "world_step_count",
            "timeline_play_count",
            "timeline_before",
            "timeline_after",
            "timeline_unchanged",
            "pvd_recording_configured",
            "pvd_extensions_enabled",
        }
        and scope.get("world_constructed") is False
        and scope.get("world_reset_count") == 0
        and scope.get("world_step_count") == 0
        and scope.get("timeline_play_count") == 0
        and _timeline_receipt(scope.get("timeline_before")) is not None
        and _timeline_receipt(scope.get("timeline_after")) is not None
        and scope["timeline_before"] == scope["timeline_after"]
        and scope["timeline_before"]["is_playing"] is False
        and scope.get("timeline_unchanged") is True
        and scope.get("pvd_recording_configured") is False
        and scope.get("pvd_extensions_enabled") is False
    )
    overlay_source_exact = (
        isinstance(overlay, Mapping)
        and overlay
        == {
            "path": calibration["path"],
            "sha256": calibration["sha256"],
            "exact_canonical_text": True,
            "api_schema_application_count": 3,
            "scalar_opinion_count": 6,
        }
    )
    target_identity = True
    collision_api_composed = True
    finite_authored_offsets = True
    strongest_opinions = True
    authoring_values_match = True
    seen_ids: set[str] = set()
    expected_by_id = {target["id"]: target for target in expected_plan["targets"]}
    if not isinstance(target_records, list):
        target_identity = collision_api_composed = finite_authored_offsets = False
        strongest_opinions = authoring_values_match = False
        target_records = []
    for record in target_records:
        if not isinstance(record, Mapping) or set(record) != {
            "id",
            "collider_path",
            "prim_type",
            "collision_enabled",
            "usd_collision_api_applied",
            "physx_collision_api_applied",
            "contact_offset",
            "rest_offset",
        }:
            target_identity = collision_api_composed = finite_authored_offsets = False
            strongest_opinions = authoring_values_match = False
            continue
        identifier = record.get("id")
        expected_target = expected_by_id.get(identifier)
        if (
            not isinstance(identifier, str)
            or identifier in seen_ids
            or expected_target is None
            or record.get("collider_path") != expected_target["collider_path"]
            or record.get("prim_type") != "Mesh"
        ):
            target_identity = False
            continue
        seen_ids.add(identifier)
        if (
            record.get("collision_enabled") is not True
            or record.get("usd_collision_api_applied") is not True
            or record.get("physx_collision_api_applied") is not True
        ):
            collision_api_composed = False
        contact_finite, contact_provenance, contact_values = _offset_checks(
            record.get("contact_offset"),
            expected_value=float(expected_target["contact_offset_m"]),
            overlay_path=calibration["path"],
        )
        rest_finite, rest_provenance, rest_values = _offset_checks(
            record.get("rest_offset"),
            expected_value=float(expected_target["rest_offset_m"]),
            overlay_path=calibration["path"],
        )
        finite_authored_offsets = finite_authored_offsets and contact_finite and rest_finite
        strongest_opinions = strongest_opinions and contact_provenance and rest_provenance
        authoring_values_match = authoring_values_match and contact_values and rest_values
        contact = record.get("contact_offset")
        rest = record.get("rest_offset")
        contact_value = (
            _finite_number(contact.get("composed_value_m")) if isinstance(contact, Mapping) else None
        )
        rest_value = _finite_number(rest.get("composed_value_m")) if isinstance(rest, Mapping) else None
        if contact_value is None or rest_value is None or rest_value > contact_value:
            finite_authored_offsets = False
    if seen_ids != set(expected_by_id) or len(target_records) != len(expected_by_id):
        target_identity = False
    checks = {
        "nonauthorizing_scope": observation.get("authorization") == AUTHORIZATION,
        "fixture_bound": fixture_bound,
        "kit_profile_bound": kit_profile_bound,
        "pvd_not_declared": pvd_not_declared,
        "input_usd_dependency_closure_stable": closure_stable,
        "resolved_usd_dependency_closure_complete": resolved_dependency_closure_complete,
        "declared_direct_inputs_bound": declared_direct_inputs_bound,
        "stage_composition_stable": stage_composition_stable,
        "no_world_or_timeline_advancement": no_world_or_timeline_advancement,
        "overlay_source_exact": overlay_source_exact,
        "target_count_and_identity": target_identity,
        "target_collision_apis_composed": collision_api_composed,
        "finite_authored_offsets_composed": finite_authored_offsets,
        "strongest_opinions_from_calibration_overlay": strongest_opinions,
        "target_authoring_values_match_plan": authoring_values_match,
    }
    payload = {
        "authority": EVALUATION_AUTHORITY,
        "classification": CLASSIFICATION,
        "decision": PASS if all(checks.values()) else NO_GO,
        "checks": checks,
        "authorization": dict(AUTHORIZATION),
        "plan_sha256": expected_plan["sha256"],
        "observation_sha256": observation["sha256"],
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}
