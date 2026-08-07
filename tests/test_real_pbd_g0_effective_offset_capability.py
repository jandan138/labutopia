from __future__ import annotations

import copy

from utils import real_pbd_g0_effective_offset_capability as capability


def _rehash(observation: dict) -> dict:
    payload = {key: value for key, value in observation.items() if key != "sha256"}
    observation["sha256"] = capability.canonical_json_sha256(payload)
    return observation


def _artifact(path: str, digest: str) -> dict:
    return {"path": path, "byte_count": 1, "sha256": digest}


def _target_manifest(plan: dict) -> dict:
    payload = {
        "authority": capability.TARGET_MANIFEST_AUTHORITY,
        "targets": [
            {
                "id": target["id"],
                "collider_path": target["collider_path"],
                "actor_name": target["actor_name"],
                "source_owner_path": target["actor_name"],
                "source_enabled_collider_paths": [target["collider_path"]],
                "source_shape_count": 1,
                "source_prim_type": "Mesh",
                "contact_offset_authored": False,
                "rest_offset_authored": False,
            }
            for target in plan["targets"]
        ],
    }
    return {**payload, "sha256": capability.canonical_json_sha256(payload)}


def _observation(plan: dict) -> dict:
    target_manifest = _target_manifest(plan)
    target_offsets = []
    for index, target in enumerate(plan["targets"]):
        manifest_target = target_manifest["targets"][index]
        target_offsets.append(
            {
                "id": target["id"],
                "collider_path": target["collider_path"],
                "actor_name": target["actor_name"],
                "actor_type": (
                    "eRIGID_STATIC" if target["id"] == "table" else "eARTICULATION_LINK"
                ),
                "pvd_actor_class": "PxActor",
                "pvd_scene_path": "/scenes/PxScene_1",
                "pvd_actor_path": f"/scenes/PxScene_1/{target['id']}",
                "pvd_shape_path": f"/scenes/PxScene_1/{target['id']}/shape",
                "sample_time_code": 0,
                "source_target_manifest_sha256": target_manifest["sha256"],
                "source_owner_path": manifest_target["source_owner_path"],
                "source_enabled_collider_paths": manifest_target[
                    "source_enabled_collider_paths"
                ],
                "source_shape_count": 1,
                "pvd_actor_shape_count": 1,
                "pvd_geometry_class": "PxGeomTriangleMesh",
                "raw_contact_offset_pvd": 0.01 + index * 0.001,
                "raw_rest_offset_pvd": 0.0,
                "pvd_length_units_per_meter": 1.0,
                "contact_offset_m": 0.01 + index * 0.001,
                "rest_offset_m": 0.0,
                "shape_flags": ["eSCENE_QUERY_SHAPE", "eSIMULATION_SHAPE"],
            }
        )
    runtime_artifacts = {
        name: {"path": f"/sealed/{name}", "sha256": character * 64}
        for name, character in zip(capability.PVD_RUNTIME_ARTIFACT_NAMES, "abcdef")
    }
    payload = {
        "authority": capability.OBSERVATION_AUTHORITY,
        "schema_version": 1,
        "classification": capability.CLASSIFICATION,
        "plan_sha256": plan["sha256"],
        "authorization": {
            "effective_offsets_resolved": False,
            "g0_go_authorized": False,
            "phase3_authorized": False,
        },
        "pvd_runtime_artifacts": runtime_artifacts,
        "pvd_extension_provenance": {
            "extension_id": "omni.physx.pvd-106.0.20",
            "extension_version": "106.0.20",
            "extension_path": "/sealed/omni.physx.pvd",
            "module_origins": {
                "extension_python": "/sealed/extension.py",
                "converter_python": "/sealed/converter.py",
                "binding": "/sealed/binding.so",
            },
        },
        "recording": {
            "capture_authority": "instrumented_world_and_timeline_v1",
            "pvd_enabled_before_scene": True,
            "bootstrap_world_reset_count": 1,
            "explicit_world_step_count": 1,
            "timeline_play_count": 1,
            "timeline_pause_count": 1,
            "world_index_before_step": 0,
            "world_index_after_step": 1,
            "pvd_enabled_after_capture": False,
            "pvd_is_recording_after_capture": False,
            "post_disable_finalization_updates": 2,
            "operation_counts": {
                "world_reset": 1,
                "world_step": 1,
                "world_play": 1,
                "world_pause": 1,
                "app_update_finalization": 2,
            },
            "timeline_event_counts": {
                "timeline_play": 1,
                "timeline_pause": 1,
                "timeline_stop": 0,
            },
            "finalized_ovd": _artifact("pvd-recording/capture.ovd", "1" * 64),
            "conversion_artifacts": [
                _artifact("pvd-converted/scene.usda", "2" * 64),
                _artifact("pvd-converted/shared.usda", "3" * 64),
                _artifact("pvd-converted/stage.usda", "4" * 64),
            ],
        },
        "pvd_scene": {
            "pvd_scene_path": "/scenes/PxScene_1",
            "pvd_scene_class": "PxScene",
            "sample_time_code": 0,
            "pvd_length_units_per_meter": 1.0,
            "source_stage_meters_per_unit": 1.0,
        },
        "target_manifest": target_manifest,
        "stage_immutability": {
            "root_layer_sha256_before": "5" * 64,
            "root_layer_sha256_after": "5" * 64,
            "session_layer_sha256_before": "6" * 64,
            "session_layer_sha256_after": "6" * 64,
            "collision_inventory_sha256_before": "7" * 64,
            "collision_inventory_sha256_after": "7" * 64,
            "unchanged": True,
        },
        "target_offsets": target_offsets,
    }
    return {**payload, "sha256": capability.canonical_json_sha256(payload)}


def test_pvd_offset_capture_stays_no_go_until_an_independent_verifier_is_bound():
    plan = capability.build_plan()
    observation = _observation(plan)

    evaluation = capability.evaluate_observation(observation, plan=plan)

    assert evaluation["decision"] == capability.NO_GO
    assert evaluation["checks"]["capture_diagnostic_complete"] is True
    assert evaluation["checks"]["independent_verifier_bound"] is False
    assert evaluation["authorization"] == {
        "effective_offsets_resolved": False,
        "g0_go_authorized": False,
        "phase3_authorized": False,
    }


def test_pvd_offset_capability_rejects_missing_target_duplicate_actor_and_invalid_offset():
    plan = capability.build_plan()

    missing = _observation(plan)
    missing["target_offsets"] = missing["target_offsets"][:-1]
    _rehash(missing)
    missing_evaluation = capability.evaluate_observation(missing, plan=plan)
    assert missing_evaluation["decision"] == capability.NO_GO
    assert missing_evaluation["checks"]["target_source_to_pvd_cardinality_bound"] is False

    duplicate = _observation(plan)
    duplicate["target_offsets"].append(copy.deepcopy(duplicate["target_offsets"][0]))
    _rehash(duplicate)
    duplicate_evaluation = capability.evaluate_observation(duplicate, plan=plan)
    assert duplicate_evaluation["decision"] == capability.NO_GO
    assert duplicate_evaluation["checks"]["target_source_to_pvd_cardinality_bound"] is False

    invalid_offset = _observation(plan)
    invalid_offset["target_offsets"][0]["contact_offset_m"] = -0.01
    _rehash(invalid_offset)
    invalid_evaluation = capability.evaluate_observation(invalid_offset, plan=plan)
    assert invalid_evaluation["decision"] == capability.NO_GO
    assert invalid_evaluation["checks"]["finite_effective_offsets"] is False


def test_pvd_offset_capability_rejects_nonexclusive_capture_lifecycle_and_authorization_upgrade():
    plan = capability.build_plan()

    observation = _observation(plan)
    observation["recording"]["explicit_world_step_count"] = 2
    observation["recording"]["pvd_enabled_after_capture"] = True
    observation["authorization"]["effective_offsets_resolved"] = True
    _rehash(observation)

    evaluation = capability.evaluate_observation(observation, plan=plan)

    assert evaluation["decision"] == capability.NO_GO
    assert evaluation["checks"]["exact_one_step_pvd_capture"] is False
    assert evaluation["checks"]["diagnostic_only_authorization"] is False


def test_pvd_offset_capability_rejects_unbound_shape_and_authored_source_target():
    plan = capability.build_plan()

    shape_outside_actor = _observation(plan)
    shape_outside_actor["target_offsets"][0]["pvd_shape_path"] = "/scenes/PxScene_1/other/shape"
    _rehash(shape_outside_actor)
    shape_evaluation = capability.evaluate_observation(shape_outside_actor, plan=plan)
    assert shape_evaluation["decision"] == capability.NO_GO
    assert shape_evaluation["checks"]["target_source_to_pvd_cardinality_bound"] is False

    authored = _observation(plan)
    authored["target_manifest"]["targets"][0]["contact_offset_authored"] = True
    payload = {
        key: value for key, value in authored["target_manifest"].items() if key != "sha256"
    }
    authored["target_manifest"]["sha256"] = capability.canonical_json_sha256(payload)
    authored["target_offsets"][0]["source_target_manifest_sha256"] = authored[
        "target_manifest"
    ]["sha256"]
    _rehash(authored)
    authored_evaluation = capability.evaluate_observation(authored, plan=plan)
    assert authored_evaluation["decision"] == capability.NO_GO
    assert authored_evaluation["checks"]["all_targets_unauthored"] is False


def test_pvd_offset_capability_rejects_nonzero_sample_or_inconsistent_si_scale():
    plan = capability.build_plan()

    nonzero_sample = _observation(plan)
    nonzero_sample["target_offsets"][0]["sample_time_code"] = 1
    _rehash(nonzero_sample)
    sample_evaluation = capability.evaluate_observation(nonzero_sample, plan=plan)
    assert sample_evaluation["decision"] == capability.NO_GO
    assert sample_evaluation["checks"]["time_zero_shape_records_complete"] is False

    wrong_units = _observation(plan)
    wrong_units["pvd_scene"]["pvd_length_units_per_meter"] = 100.0
    _rehash(wrong_units)
    units_evaluation = capability.evaluate_observation(wrong_units, plan=plan)
    assert units_evaluation["decision"] == capability.NO_GO
    assert units_evaluation["checks"]["pvd_unit_scale_bound"] is False


def test_pvd_offset_capability_rejects_stage_drift_and_unbound_extension_origin():
    plan = capability.build_plan()

    drift = _observation(plan)
    drift["stage_immutability"]["unchanged"] = False
    drift["stage_immutability"]["root_layer_sha256_after"] = "8" * 64
    _rehash(drift)
    drift_evaluation = capability.evaluate_observation(drift, plan=plan)
    assert drift_evaluation["decision"] == capability.NO_GO
    assert drift_evaluation["checks"]["stage_input_unchanged"] is False

    provenance = _observation(plan)
    provenance["pvd_extension_provenance"]["module_origins"].pop("binding")
    _rehash(provenance)
    provenance_evaluation = capability.evaluate_observation(provenance, plan=plan)
    assert provenance_evaluation["decision"] == capability.NO_GO
    assert provenance_evaluation["checks"]["pvd_extension_provenance_bound"] is False


def test_pvd_offset_capability_rejects_boolean_plan_and_lifecycle_type_confusion():
    plan = capability.build_plan()
    malformed_plan = copy.deepcopy(plan)
    malformed_plan["schema_version"] = True
    plan_payload = {key: value for key, value in malformed_plan.items() if key != "sha256"}
    malformed_plan["sha256"] = capability.canonical_json_sha256(plan_payload)
    try:
        capability.validate_plan(malformed_plan)
    except ValueError as exc:
        assert str(exc) == "real_pbd_g0_effective_offset_capability_plan_invalid"
    else:
        raise AssertionError("boolean PVD plan schema unexpectedly accepted")

    observation = _observation(plan)
    observation["recording"]["explicit_world_step_count"] = True
    observation["recording"]["operation_counts"]["world_step"] = True
    _rehash(observation)
    evaluation = capability.evaluate_observation(observation, plan=plan)
    assert evaluation["decision"] == capability.NO_GO
    assert evaluation["checks"]["exact_one_step_pvd_capture"] is False


def test_pvd_offset_capability_requires_a_canonical_observation_hash():
    plan = capability.build_plan()
    observation = _observation(plan)
    observation["recording"]["world_index_after_step"] = 2

    try:
        capability.evaluate_observation(observation, plan=plan)
    except ValueError as exc:
        assert str(exc) == "real_pbd_g0_effective_offset_capability_observation_invalid"
    else:
        raise AssertionError("tampered PVD observation unexpectedly accepted")
