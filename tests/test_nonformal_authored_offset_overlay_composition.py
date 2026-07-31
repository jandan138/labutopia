from __future__ import annotations

import copy
from pathlib import Path

from utils import nonformal_authored_offset_overlay_composition as composition


REPO_ROOT = Path(__file__).resolve().parents[1]
OVERLAY_PATH = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_g0_finite_target_offsets_calibration_v2.usda"
)


def _fixture() -> dict:
    overlay_stack = [
        {
            "id": composition.OVERLAY_PROFILE_ID,
            "path": "/fixture/calibration.usda",
            "sha256": "b" * 64,
        },
        {
            "id": "hidden_cube_collision_disable",
            "path": "/fixture/hidden-cube.usda",
            "sha256": "a" * 64,
        },
    ]
    profile = {
        "authority": composition.OVERLAY_PROFILE_AUTHORITY,
        "id": composition.OVERLAY_PROFILE_ID,
        "overlay_stack": overlay_stack,
    }
    return {
        "asset": {"path": "/fixture/asset.usda", "sha256": "c" * 64},
        "robot_asset": {"path": "/fixture/robot.usd", "sha256": "d" * 64},
        "overlay_profile": profile,
        "overlay_profile_sha256": composition.canonical_json_sha256(profile),
    }


def _kit_profile() -> dict:
    return {
        "path": "/fixture/authored-offsets.kit",
        "sha256": "e" * 64,
        "pvd_extension_declared": False,
    }


def _closure() -> dict:
    layers = sorted([
        {
            "identifier": "fixture.usda",
            "real_path": "/fixture/asset.usda",
            "sha256": "c" * 64,
        },
        {
            "identifier": "calibration.usda",
            "real_path": "/fixture/calibration.usda",
            "sha256": "b" * 64,
        },
        {
            "identifier": "hidden-cube.usda",
            "real_path": "/fixture/hidden-cube.usda",
            "sha256": "a" * 64,
        },
        {
            "identifier": "robot.usd",
            "real_path": "/fixture/robot.usd",
            "sha256": "d" * 64,
        },
    ], key=lambda item: item["real_path"])
    payload = {"layers": layers}
    return {**payload, "sha256": composition.canonical_json_sha256(payload)}


def _resolved_dependency_closure(fixture: dict, stack: list[dict]) -> dict:
    entries = [
        {"id": "fixture_asset", **fixture["asset"]},
        {"id": "robot_asset", **fixture["robot_asset"]},
        *(
            {"id": item["id"], "path": item["path"], "sha256": item["sha256"]}
            for item in stack
        ),
    ]
    files = [
        {"path": item["path"], "byte_count": 1, "sha256": item["sha256"]}
        for item in entries
    ]
    files.sort(key=lambda item: item["path"])
    payload = {
        "entries": entries,
        "files": files,
        "runtime_mdl_files": [],
        "runtime_mdl_builtin_modules": [],
        "texture_unresolved": [],
        "unresolved": [],
    }
    return {**payload, "sha256": composition.canonical_json_sha256(payload)}


def _observation(plan: dict, fixture: dict, kit_profile: dict) -> dict:
    calibration = next(
        item
        for item in fixture["overlay_profile"]["overlay_stack"]
        if item["id"] == composition.OVERLAY_PROFILE_ID
    )
    calibration_path = calibration["path"]
    targets = []
    for target in plan["targets"]:
        offsets = {}
        for field in ("contact_offset_m", "rest_offset_m"):
            value = target[field]
            offsets[field.removesuffix("_m")] = {
                "authored": True,
                "composed_value_m": value,
                "property_stack_layer_paths": [calibration_path, "/fixture/base.usda"],
                "strongest_property_stack_default_m": value,
            }
        targets.append(
            {
                "id": target["id"],
                "collider_path": target["collider_path"],
                "prim_type": "Mesh",
                "collision_enabled": True,
                "usd_collision_api_applied": True,
                "physx_collision_api_applied": True,
                **offsets,
            }
        )
    closure = _closure()
    overlay_stack = fixture["overlay_profile"]["overlay_stack"]
    cube_only_stack = [
        item for item in overlay_stack if item["id"] == "hidden_cube_collision_disable"
    ]
    payload = {
        "authority": composition.OBSERVATION_AUTHORITY,
        "schema_version": 1,
        "classification": composition.CLASSIFICATION,
        "plan_sha256": plan["sha256"],
        "authorization": dict(composition.AUTHORIZATION),
        "fixture": fixture,
        "kit_profile": kit_profile,
        "input_usd_dependency_closures": {"before": closure, "after": closure},
        "resolved_usd_dependency_closures": {
            "cube_only_baseline_v1": {
                "before": _resolved_dependency_closure(fixture, cube_only_stack),
                "after": _resolved_dependency_closure(fixture, cube_only_stack),
            },
            "finite_target_offsets_calibration_v2": {
                "before": _resolved_dependency_closure(fixture, overlay_stack),
                "after": _resolved_dependency_closure(fixture, overlay_stack),
            },
        },
        "stage": {
            "meters_per_unit": 1.0,
            "up_axis": "Z",
            "session_sublayer_paths": [
                item["path"] for item in fixture["overlay_profile"]["overlay_stack"]
            ],
            "robot_reference_ready_before_treatment": True,
            "cube_collision_disabled": True,
            "root_layer_sha256_before": "1" * 64,
            "root_layer_sha256_after": "1" * 64,
            "session_layer_sha256_before": "2" * 64,
            "session_layer_sha256_after": "2" * 64,
            "composition_unchanged": True,
        },
        "runtime_scope": {
            "world_constructed": False,
            "world_reset_count": 0,
            "world_step_count": 0,
            "timeline_play_count": 0,
            "timeline_before": {"is_playing": False, "time_s": 0.0},
            "timeline_after": {"is_playing": False, "time_s": 0.0},
            "timeline_unchanged": True,
            "pvd_recording_configured": False,
            "pvd_extensions_enabled": False,
        },
        "overlay_layer": {
            "path": calibration_path,
            "sha256": calibration["sha256"],
            "exact_canonical_text": True,
            "api_schema_application_count": 3,
            "scalar_opinion_count": 6,
        },
        "targets": targets,
    }
    return {**payload, "sha256": composition.canonical_json_sha256(payload)}


def _rehash(observation: dict) -> dict:
    payload = {key: value for key, value in observation.items() if key != "sha256"}
    observation["sha256"] = composition.canonical_json_sha256(payload)
    return observation


def test_overlay_is_an_exact_allowlisted_authored_offset_treatment():
    assert OVERLAY_PATH.read_text(encoding="ascii") == composition.expected_overlay_usda()


def test_plan_pins_the_approved_finite_values_and_never_authorizes_g0():
    plan = composition.build_plan()

    assert [(target["id"], target["contact_offset_m"], target["rest_offset_m"]) for target in plan["targets"]] == [
        ("left_finger", 0.001, 0.0),
        ("right_finger", 0.001, 0.0),
        ("table", 0.00164, 0.0),
    ]
    assert plan["authorization"] == composition.AUTHORIZATION
    assert composition.validate_plan(plan) == plan


def test_composed_authored_overlay_observation_passes_without_effective_offset_claims():
    plan = composition.build_plan()
    fixture = _fixture()
    kit_profile = _kit_profile()
    observation = _observation(plan, fixture, kit_profile)

    evaluation = composition.evaluate_observation(
        observation,
        plan=plan,
        fixture=fixture,
        kit_profile=kit_profile,
    )

    assert evaluation["decision"] == composition.PASS
    assert all(evaluation["checks"].values())
    assert evaluation["authorization"] == composition.AUTHORIZATION
    assert "effective_offsets_m" not in evaluation


def test_composed_authored_overlay_rejects_authority_upgrade_and_bad_provenance():
    plan = composition.build_plan()
    fixture = _fixture()
    kit_profile = _kit_profile()

    authority_upgrade = _observation(plan, fixture, kit_profile)
    authority_upgrade["authorization"]["g0_go_authorized"] = True
    _rehash(authority_upgrade)
    authority_evaluation = composition.evaluate_observation(
        authority_upgrade,
        plan=plan,
        fixture=fixture,
        kit_profile=kit_profile,
    )
    assert authority_evaluation["decision"] == composition.NO_GO
    assert authority_evaluation["checks"]["nonauthorizing_scope"] is False

    wrong_layer = _observation(plan, fixture, kit_profile)
    wrong_layer["targets"][0]["contact_offset"]["property_stack_layer_paths"][0] = "/fixture/base.usda"
    _rehash(wrong_layer)
    provenance_evaluation = composition.evaluate_observation(
        wrong_layer,
        plan=plan,
        fixture=fixture,
        kit_profile=kit_profile,
    )
    assert provenance_evaluation["decision"] == composition.NO_GO
    assert provenance_evaluation["checks"]["strongest_opinions_from_calibration_overlay"] is False


def test_composed_authored_overlay_rejects_world_advancement_and_value_drift():
    plan = composition.build_plan()
    fixture = _fixture()
    kit_profile = _kit_profile()
    observation = _observation(plan, fixture, kit_profile)
    observation["runtime_scope"]["world_step_count"] = 1
    observation["targets"][2]["contact_offset"]["composed_value_m"] = 0.02
    _rehash(observation)

    evaluation = composition.evaluate_observation(
        observation,
        plan=plan,
        fixture=fixture,
        kit_profile=kit_profile,
    )

    assert evaluation["decision"] == composition.NO_GO
    assert evaluation["checks"]["no_world_or_timeline_advancement"] is False
    assert evaluation["checks"]["target_authoring_values_match_plan"] is False


def test_composed_authored_overlay_rejects_missing_direct_input_closure_binding():
    plan = composition.build_plan()
    fixture = _fixture()
    kit_profile = _kit_profile()
    observation = _observation(plan, fixture, kit_profile)
    closure = observation["input_usd_dependency_closures"]["before"]
    closure["layers"] = closure["layers"][:-1]
    closure["sha256"] = composition.canonical_json_sha256({"layers": closure["layers"]})
    observation["input_usd_dependency_closures"]["after"] = copy.deepcopy(closure)
    _rehash(observation)

    evaluation = composition.evaluate_observation(
        observation,
        plan=plan,
        fixture=fixture,
        kit_profile=kit_profile,
    )

    assert evaluation["decision"] == composition.NO_GO
    assert evaluation["checks"]["declared_direct_inputs_bound"] is False
