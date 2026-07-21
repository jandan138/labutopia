from __future__ import annotations

import copy
import hashlib
import json

import numpy as np
import pytest

from utils.controlled_contact import canonical_json_sha256
from utils.real_pbd_grasp_v2 import (
    G2BilateralCertificate,
    ParticleRuntimeIdentityTracker,
    build_g2_baseline_contact_receipt,
    build_g2_applied_action_receipt,
    build_g2_classification_receipt,
    build_g2_execution_context,
    build_g2_immediate_report_envelope,
    build_g2_sensor_pair_receipt,
    build_g2_source_state_receipt,
    build_g2f_one_use_authorization,
    build_g2f_successor_launch_manifest,
    build_g2f_launch_binding,
    build_stage_evidence,
    build_g2_trajectory_spec,
    build_stage_artifact,
    build_source_stage_authoring_snapshot,
    consume_g2f_one_use_authorization,
    evaluate_g0_clearance_certificate,
    evaluate_g1_baseline_pair,
    evaluate_g1_treatment,
    evaluate_g2_substep,
    evaluate_source_stage_authoring_diff,
    evaluate_static_pbd_fixture_preflight,
    serialize_stage_artifact,
)


SOURCE_SHELL = "/World/beaker2/mesh"
SOURCE_WRAPPER = "/World/beaker2/FluidSafeWrapperCanonical/panel_000"
TABLE = "/World/table/surface/mesh"
LEFT_PAD = "/World/Franka/panda_leftfinger/pad"
RIGHT_PAD = "/World/Franka/panda_rightfinger/pad"
HAND = "/World/Franka/panda_hand/collision"
PARTICLES = "/World/InternDataParityFluid/Particles"


def _sha(character: str) -> str:
    return character * 64


def _hashed(payload: dict, *, field: str = "evidence_sha256") -> dict:
    return {**payload, field: canonical_json_sha256(payload)}


def _g0_certificate() -> dict:
    colliders = (
        LEFT_PAD,
        RIGHT_PAD,
        HAND,
        SOURCE_SHELL,
        SOURCE_WRAPPER,
        TABLE,
    )
    return {
        "authority": "real_pbd_g0_clearance_certificate_v1",
        "fixture": {
            "usd_dependency_closure_sha256": _sha("a"),
            "composed_collision_inventory_sha256": _sha("b"),
            "source_actor_path": "/World/beaker2",
            "particle_path": PARTICLES,
            "source_external_shell_paths": [SOURCE_SHELL],
            "source_internal_wrapper_paths": [SOURCE_WRAPPER],
            "support_collider_paths": [TABLE],
            "finger_pad_collider_paths": {
                "left": [LEFT_PAD],
                "right": [RIGHT_PAD],
            },
            "hand_collider_paths": [HAND],
        },
        "effective_offsets_m": {
            path: {
                "contact_offset_m": 0.001,
                "rest_offset_m": 0.0,
                "authority": "runtime_effective_physx_v1",
            }
            for path in colliders
        },
        "load_input_authority": {
            "particle_count": 3,
            "particle_density_or_mass_authority": "runtime_readback_required_v1",
            "source_dry_mass_kg": 0.02,
            "gravity_world_m_s2": [0.0, 0.0, -9.81],
            "solver_settings_sha256": _sha("c"),
            "runtime_filled_load_verified": False,
        },
        "candidate_set": {
            "authority": "g0_predeclared_finite_candidate_set_v1",
            "selected_candidate_id": "top_down_candidate_01",
            "candidates": [
                {
                    "authority": "real_pbd_g0_candidate_v1",
                    "id": "top_down_candidate_01",
                    "target_spec_sha256": _sha("d"),
                    "close_endpoint_m": 0.028,
                    "source_frame_grasp_offset_m": [0.001, 0.0, 0.01],
                    "approach_direction_world": [0.0, 0.0, -1.0],
                    "pregrasp_distance_m": 0.08,
                    "insert_distance_m": 0.02,
                    "tool_orientation_wxyz": [0.0, 0.0, 1.0, 0.0],
                    "control_target_offset_world_m": [0.0, 0.0, -0.0034],
                    "finger_joint_indices": [7, 8],
                    "close_speed_m_s": 0.002,
                    "bilateral_policy": {
                        "required_consecutive_steps": 2,
                        "maximum_one_sided_steps": 0,
                    },
                    "tracking_envelope": {
                        "maximum_position_error_m": 0.0005,
                        "maximum_orientation_error_degrees": 0.5,
                    },
                    "precontact_pad_shell_clearance_m": {
                        "left": 0.004,
                        "right": 0.004,
                    },
                    "prohibited_sweeps": [
                        {
                            "collider_paths": [LEFT_PAD, SOURCE_WRAPPER],
                            "minimum_signed_clearance_m": 0.002,
                            "sample_count": 5,
                        },
                        {
                            "collider_paths": [RIGHT_PAD, SOURCE_WRAPPER],
                            "minimum_signed_clearance_m": 0.002,
                            "sample_count": 5,
                        },
                        {
                            "collider_paths": [HAND, SOURCE_SHELL],
                            "minimum_signed_clearance_m": 0.003,
                            "sample_count": 5,
                        },
                        {
                            "collider_paths": [LEFT_PAD, TABLE],
                            "minimum_signed_clearance_m": 0.010,
                            "sample_count": 5,
                        },
                        {
                            "collider_paths": [RIGHT_PAD, TABLE],
                            "minimum_signed_clearance_m": 0.010,
                            "sample_count": 5,
                        },
                    ],
                }
            ],
        },
    }


def test_g0_requires_composed_geometry_offsets_and_strict_clearance():
    certificate = _g0_certificate()

    result = evaluate_g0_clearance_certificate(certificate)

    assert result["decision"] == "G0_GO"
    assert result["selected_candidate_id"] == "top_down_candidate_01"
    assert result["g3_g4_filled_load_authorized"] is False
    assert result["checks"]["all_prohibited_sweeps_strictly_positive"] is True

    zero_margin = copy.deepcopy(certificate)
    zero_margin["candidate_set"]["candidates"][0]["prohibited_sweeps"][0][
        "minimum_signed_clearance_m"
    ] = 0.0
    assert evaluate_g0_clearance_certificate(zero_margin)["decision"] == "G0_NO_GO"


def test_g0_fails_closed_for_unresolved_offsets_or_missing_wrapper_geometry():
    unresolved = _g0_certificate()
    unresolved["effective_offsets_m"][LEFT_PAD]["authority"] = "unresolved"
    with pytest.raises(ValueError, match="real_pbd_g0"):
        evaluate_g0_clearance_certificate(unresolved)

    missing_wrapper = _g0_certificate()
    missing_wrapper["fixture"]["source_internal_wrapper_paths"] = []
    with pytest.raises(ValueError, match="real_pbd_g0"):
        evaluate_g0_clearance_certificate(missing_wrapper)


def _source_matrix(x: float) -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [x, 0.075, 0.8233382266115852, 1.0],
    ]


def _source_pose_hash(matrix: list[list[float]]) -> str:
    values = np.ascontiguousarray(matrix, dtype=np.dtype("<f8"))
    return hashlib.sha256(values.tobytes(order="C")).hexdigest()


def _g1_report(
    treatment: str,
    *,
    translation_m: float = 0.0,
    payload_available: bool = True,
) -> dict:
    records = []
    for local_step in range(4):
        x = translation_m * local_step / 3.0
        matrix = _source_matrix(x)
        record = {
            "reset_epoch": 0,
            "local_step": local_step,
            "world_step": 100 + local_step,
            "world_time_s": local_step / 600.0,
            "source_root_matrix_m": matrix,
            "source_com_position_m": [x, 0.075, 0.8233382266115852],
            "source_axis_tilt_degrees": 0.0,
            "linear_velocity_m_s": [0.0, 0.0, 0.0],
            "angular_velocity_rad_s": [0.0, 0.0, 0.0],
            "collision_inventory_sha256": _sha("b"),
            "collision_state_sha256": _sha("e"),
            "contact_pairs": [[SOURCE_SHELL, TABLE]],
            "source_pose_sha256": _source_pose_hash(matrix),
            "source_frame_pose_sha256": _source_pose_hash(matrix),
        }
        if treatment == "filled":
            record.update(
                {
                    "particle_count": 3,
                    "particle_ids_sha256": _sha("f"),
                    "particle_id_coverage_count": 3,
                    "particle_positions_sha256": _sha("a"),
                }
            )
        records.append(record)
    return {
        "authority": "real_pbd_g1_passive_baseline_v1",
        "treatment": treatment,
        "fixture_identity": {
            "usd_dependency_closure_sha256": _sha("a"),
            "composed_collision_inventory_sha256": _sha("b"),
            "physics_settings_sha256": _sha("c"),
            "source_initial_pose_sha256": _source_pose_hash(_source_matrix(0.0)),
            "source_actor_path": "/World/beaker2",
            "particle_path": PARTICLES,
        },
        "schedule": {
            "physics_dt_s": 1.0 / 600.0,
            "pre_roll_steps": 1,
            "hold_steps": 2,
        },
        "preworld_mutations": (
            [
                {
                    "phase": "pre_world",
                    "operation": "set_active",
                    "path": PARTICLES,
                    "value": False,
                }
            ]
            if treatment == "dry"
            else []
        ),
        "records": records,
        "particle_authority": (
            {
                "authority": "stable_runtime_particle_ids_v1",
                "expected_count": 3,
                "stable_ids_sha256": _sha("f"),
                "particle_id_manifest_sha256": _sha("a"),
            }
            if treatment == "filled"
            else {"status": "NOT_APPLICABLE_BY_DRY_TREATMENT"}
        ),
        "filled_payload_authority": (
            {
                "authority": "runtime_filled_payload_measurement_v1",
                "source_dry_mass_kg": 0.02,
                "particle_mass_kg": 0.01,
                "effective_filled_mass_kg": 0.03,
                "particle_count": 3,
                "gravity_world_m_s2": [0.0, 0.0, -9.81],
            }
            if treatment == "filled" and payload_available
            else {"status": "UNAVAILABLE"}
        ),
    }


G1_LIMITS = {
    "maximum_translation_m": 0.001,
    "maximum_tilt_degrees": 0.5,
    "maximum_linear_speed_m_s": 0.002,
    "maximum_angular_speed_rad_s": 0.02,
    "maximum_contact_set_changes": 0,
    "maximum_collision_state_changes": 0,
    "maximum_differential_translation_m": 0.0005,
    "maximum_differential_tilt_degrees": 0.1,
    "maximum_differential_linear_speed_m_s": 0.001,
    "maximum_differential_angular_speed_rad_s": 0.01,
}


def test_g1_compares_same_fixture_and_seals_dry_filled_authority():
    result = evaluate_g1_baseline_pair(
        dry_report=_g1_report("dry"),
        filled_report=_g1_report("filled"),
        limits=G1_LIMITS,
    )

    assert result["decision"] == "G1_GO"
    assert result["g2_f_authorized"] is True
    assert result["g3_g4_filled_load_authorized"] is True
    assert result["checks"]["same_fixture_identity"] is True
    assert result["checks"]["stable_particle_id_coverage"] is True

    mismatch = _g1_report("filled")
    mismatch["fixture_identity"]["physics_settings_sha256"] = _sha("f")
    result = evaluate_g1_baseline_pair(
        dry_report=_g1_report("dry"),
        filled_report=mismatch,
        limits=G1_LIMITS,
    )
    assert result["decision"] == "G1_NO_GO"
    assert result["checks"]["same_fixture_identity"] is False


def test_g1_keeps_g2_close_available_but_blocks_lift_pour_without_load_authority():
    result = evaluate_g1_baseline_pair(
        dry_report=_g1_report("dry"),
        filled_report=_g1_report("filled", payload_available=False),
        limits=G1_LIMITS,
    )

    assert result["decision"] == "G1_GO"
    assert result["g2_f_authorized"] is True
    assert result["g3_g4_filled_load_authorized"] is False

    differential_failure = evaluate_g1_baseline_pair(
        dry_report=_g1_report("dry"),
        filled_report=_g1_report("filled", translation_m=0.0008),
        limits=G1_LIMITS,
    )
    assert differential_failure["decision"] == "G1_NO_GO"
    assert differential_failure["checks"]["differential_bounds"] is False


def test_g1_treatment_decisions_can_be_sealed_before_the_pair_comparison():
    dry = evaluate_g1_treatment(report=_g1_report("dry"), limits=G1_LIMITS)
    filled = evaluate_g1_treatment(
        report=_g1_report("filled", payload_available=False), limits=G1_LIMITS
    )

    assert dry["decision"] == "G1_D_GO"
    assert dry["g2_eligible"] is True
    assert filled["decision"] == "G1_F_GO"
    assert filled["g2_eligible"] is True
    assert filled["g3_g4_filled_load_authorized"] is False

    invalid_dry = _g1_report("dry")
    invalid_dry["preworld_mutations"] = []
    assert evaluate_g1_treatment(report=invalid_dry, limits=G1_LIMITS)[
        "decision"
    ] == "G1_D_NO_GO"


def _pair_record(
    first: str,
    second: str,
    *,
    contact_class: str,
    side: str | None = None,
    current: bool = True,
    transient: bool = False,
) -> dict:
    return {
        "class": contact_class,
        "side": side,
        "pair": {"collider_paths": sorted([first, second])},
        "current": current,
        "transient": transient,
        "gate_failures": [],
    }


def _full_report(pairs: list[tuple[str, str]], *, physics_step: int = 10) -> dict:
    return _hashed(
        {
            "authority": "full_contact_report_step_v1",
            "physics_index": physics_step,
            "current_pairs": [
                [
                    {"collider_path": first, "proto_index": 0xFFFFFFFF},
                    {"collider_path": second, "proto_index": 0xFFFFFFFF},
                ]
                for first, second in pairs
            ],
            "occurrences": [],
        }
    )


def _classification(
    records: list[dict], *, phase: str = "CLOSE", physics_step: int = 10
) -> dict:
    class_counts: dict[str, int] = {}
    for record in records:
        class_counts[record["class"]] = class_counts.get(record["class"], 0) + 1
    terminal_kind = (
        "PROTOCOL_FAILURE"
        if class_counts.get("UNKNOWN_CONTACT", 0)
        else "PHYSICAL_CONTACT_FAILURE"
        if class_counts.get("PROHIBITED_CONTACT", 0)
        else None
    )
    return _hashed(
        {
            "authority": "controlled_contact_complete_immediate_report_v1",
            "physics_step": physics_step,
            "phase": phase,
            "records": records,
            "class_counts": class_counts,
            "terminal_kind": terminal_kind,
            "source_motion_authority_valid": True,
        }
    )


def _raw_physx_report(
    pairs: list[tuple[str, str]], *, physics_step: int = 10
) -> dict:
    current_pairs = [
        [
            {"collider_path": first, "proto_index": 0xFFFFFFFF},
            {"collider_path": second, "proto_index": 0xFFFFFFFF},
        ]
        for first, second in pairs
    ]
    occurrences = []
    raw_headers = []
    for index, (first, second) in enumerate(pairs):
        header = {
            "type": "PERSIST",
            "stage_id": 1,
            "actor0": "/World/a",
            "actor1": "/World/b",
            "collider0": first,
            "collider1": second,
            "proto_index0": 0xFFFFFFFF,
            "proto_index1": 0xFFFFFFFF,
            "contact_data_offset": 0,
            "num_contact_data": 0,
            "friction_anchors_offset": 0,
            "num_friction_anchors_data": 0,
        }
        raw_headers.append(copy.deepcopy(header))
        occurrences.append(
            {
                "canonical_pair": copy.deepcopy(current_pairs[index]),
                "event_sequence": "PERSIST",
                "current": True,
                "transient": False,
                "bootstrap": False,
                "fragments": [
                    {
                        "header": copy.deepcopy(header),
                        "contact_data": [],
                        "friction_anchors": [],
                    }
                ],
                "headers": [copy.deepcopy(header)],
                "contact_data": [],
                "friction_anchors": [],
            }
        )
    return {
        "authority": "physx_immediate_full_contact_report_v1",
        "physics_index": physics_step,
        "header_count": len(pairs),
        "contact_data_count": 0,
        "friction_anchor_count": 0,
        "range_partition_valid": True,
        "event_sequences": ["PERSIST"] * len(pairs),
        "occurrence_count": len(occurrences),
        "occurrences": occurrences,
        "current_pair_count": len(current_pairs),
        "current_pairs": current_pairs,
        "bootstrap_pair_count": 0,
        "immediate_read_index": 0,
        "immediate_read_count": 1,
        "raw_headers": raw_headers,
        "raw_contact_data": [],
        "raw_friction_anchors": [],
    }


def _append_transient_raw_occurrence(raw: dict, first: str, second: str) -> None:
    headers = []
    for event in ("FOUND", "LOST"):
        headers.append(
            {
                "type": event,
                "stage_id": 1,
                "actor0": "/World/a",
                "actor1": "/World/b",
                "collider0": first,
                "collider1": second,
                "proto_index0": 0xFFFFFFFF,
                "proto_index1": 0xFFFFFFFF,
                "contact_data_offset": 0,
                "num_contact_data": 0,
                "friction_anchors_offset": 0,
                "num_friction_anchors_data": 0,
            }
        )
    raw["raw_headers"].extend(copy.deepcopy(headers))
    raw["header_count"] = len(raw["raw_headers"])
    raw["event_sequences"].append("FOUND,LOST")
    raw["occurrences"].append(
        {
            "canonical_pair": [
                {"collider_path": first, "proto_index": 0xFFFFFFFF},
                {"collider_path": second, "proto_index": 0xFFFFFFFF},
            ],
            "event_sequence": "FOUND,LOST",
            "current": False,
            "transient": True,
            "bootstrap": False,
            "headers": copy.deepcopy(headers),
            "contact_data": [],
            "friction_anchors": [],
            "fragments": [
                {
                    "header": copy.deepcopy(header),
                    "contact_data": [],
                    "friction_anchors": [],
                }
                for header in headers
            ],
        }
    )
    raw["occurrence_count"] = len(raw["occurrences"])


def _sealed_g2_context() -> tuple[dict, dict]:
    certificate = _g0_certificate()
    g0_decision = evaluate_g0_clearance_certificate(certificate)
    trajectory = build_g2_trajectory_spec(
        candidate=certificate["candidate_set"]["candidates"][0],
        live_source_pose={
            "position_world_m": [0.295, 0.075, 0.8233382266115852],
            "orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
        },
    )
    baseline = build_g2_baseline_contact_receipt(
        run_id="g2-test-run",
        reset_epoch=0,
        fixture_identity_sha256=canonical_json_sha256(g0_decision["fixture_identity"]),
        reset_raw_physx_report=_raw_physx_report([(SOURCE_SHELL, TABLE)], physics_step=9),
        post_baseline_source_pose={
            "position_world_m": [0.295, 0.075, 0.8233382266115852],
            "orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
        },
        source_external_shell_paths=[SOURCE_SHELL],
        support_collider_paths=[TABLE],
        finger_pad_collider_paths={"left": [LEFT_PAD], "right": [RIGHT_PAD]},
        hand_collider_paths=[HAND],
        source_wrapper_collider_paths=[SOURCE_WRAPPER],
        particle_collider_paths=[PARTICLES],
    )
    return (
        build_g2_execution_context(
            run_id="g2-test-run",
            reset_epoch=0,
            g0_certificate=certificate,
            g0_decision=g0_decision,
            trajectory=trajectory,
            baseline_receipt=baseline,
        ),
        trajectory,
    )


def _sealed_g2_action_receipt(
    context: dict, envelope: dict, *, phase: str = "CLOSE", interval_index: int = 2
) -> dict:
    expected = context["action_expectations"][phase]
    action = next(
        item for item in context["trajectory"]["actions"] if item["phase"] == phase
    )
    payload = {
        "authority": "controlled_action_applied_receipt_v1",
        "phase": phase,
        "semantic_action_kind": expected["semantic_action_kind"],
        "channel": expected["channel"],
        "action_sha256": _sha("b"),
        "target_token_sha256": expected["target_token_sha256"],
        "target_token": copy.deepcopy(action["target_token"]),
        "proposal_sha256": _sha("c"),
        "commit_sha256": _sha("d"),
        "control_index": 1,
        "action_index": 1,
        "apply_index": 1,
        "interval_index": interval_index,
        "controller_phase": phase,
        "applied": True,
        "normal_api_return": True,
        "physics_steps_before_receipt": 0,
    }
    return build_g2_applied_action_receipt(
        execution_context=context,
        immediate_report_envelope=envelope,
        applied_action_receipt=_hashed(payload, field="sha256"),
    )


def test_g2_sealed_evidence_covers_every_occurrence_and_binds_the_launch_context():
    context, _ = _sealed_g2_context()
    pairs = [
        (SOURCE_SHELL, TABLE),
        (LEFT_PAD, SOURCE_SHELL),
        (RIGHT_PAD, SOURCE_SHELL),
    ]
    envelope = build_g2_immediate_report_envelope(
        _raw_physx_report(pairs),
        execution_context=context,
        phase="CLOSE",
        interval_index=2,
        substep_slot=1,
        substeps_per_interval=20,
    )
    classification = build_g2_classification_receipt(
        immediate_report_envelope=envelope,
        classification=_classification(
            [
                _pair_record(SOURCE_SHELL, TABLE, contact_class="BACKGROUND"),
                _pair_record(
                    LEFT_PAD,
                    SOURCE_SHELL,
                    contact_class="INTENDED_CLOSE_CONTACT",
                    side="left",
                ),
                _pair_record(
                    RIGHT_PAD,
                    SOURCE_SHELL,
                    contact_class="INTENDED_CLOSE_CONTACT",
                    side="right",
                ),
            ]
        ),
    )
    legacy_background = _pair_record(SOURCE_SHELL, TABLE, contact_class="BACKGROUND")
    legacy_background.pop("current")
    legacy_background.pop("transient")
    legacy_normalized = build_g2_classification_receipt(
        immediate_report_envelope=envelope,
        classification=_classification(
            [
                legacy_background,
                _pair_record(
                    LEFT_PAD,
                    SOURCE_SHELL,
                    contact_class="INTENDED_CLOSE_CONTACT",
                    side="left",
                ),
                _pair_record(
                    RIGHT_PAD,
                    SOURCE_SHELL,
                    contact_class="INTENDED_CLOSE_CONTACT",
                    side="right",
                ),
            ]
        ),
    )
    assert legacy_normalized["records"][0]["current"] is True
    assert legacy_normalized["records"][0]["transient"] is False
    sensors = build_g2_sensor_pair_receipt(
        immediate_report_envelope=envelope,
        normalized_sensor_contacts=[
            {
                "physics_step": 10,
                "collider0_path": LEFT_PAD,
                "collider1_path": SOURCE_SHELL,
            },
            {
                "physics_step": 10,
                "collider0_path": RIGHT_PAD,
                "collider1_path": SOURCE_SHELL,
            },
        ],
    )
    source_state = build_g2_source_state_receipt(
        execution_context=context,
        physics_step=10,
        interval_index=2,
        substep_slot=1,
        phase="CLOSE",
        pre=_source_state_receipt(10)["pre"],
        post=_source_state_receipt(10)["post"],
    )

    result = evaluate_g2_substep(
        execution_context=context,
        immediate_report_envelope=envelope,
        classification_receipt=classification,
        sensor_receipt=sensors,
        source_state_receipt=source_state,
        action_receipt=_sealed_g2_action_receipt(context, envelope),
    )

    assert result["terminal_kind"] is None
    assert result["current_intended_sides"] == ["left", "right"]

    replayed_action = _sealed_g2_action_receipt(context, envelope)
    replayed_action["physics_step"] = 11
    replayed_action["evidence_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in replayed_action.items()
            if key != "evidence_sha256"
        }
    )
    with pytest.raises(ValueError, match="real_pbd_g2_action_receipt_binding_invalid"):
        evaluate_g2_substep(
            execution_context=context,
            immediate_report_envelope=envelope,
            classification_receipt=classification,
            sensor_receipt=sensors,
            source_state_receipt=source_state,
            action_receipt=replayed_action,
        )

    tampered_target = _sealed_g2_action_receipt(context, envelope)
    inner_action = tampered_target["applied_action_receipt"]
    inner_action["target_token"]["tampered"] = True
    inner_action["sha256"] = canonical_json_sha256(
        {key: value for key, value in inner_action.items() if key != "sha256"}
    )
    tampered_target["applied_action_receipt_sha256"] = inner_action["sha256"]
    tampered_target["evidence_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in tampered_target.items()
            if key != "evidence_sha256"
        }
    )
    with pytest.raises(ValueError, match="real_pbd_g2_action_receipt_invalid"):
        evaluate_g2_substep(
            execution_context=context,
            immediate_report_envelope=envelope,
            classification_receipt=classification,
            sensor_receipt=sensors,
            source_state_receipt=source_state,
            action_receipt=tampered_target,
        )

    with pytest.raises(ValueError, match="real_pbd_g2_immediate_report_prebaseline_invalid"):
        build_g2_immediate_report_envelope(
            _raw_physx_report([(SOURCE_SHELL, TABLE)], physics_step=9),
            execution_context=context,
            phase="CLOSE",
            interval_index=2,
            substep_slot=1,
            substeps_per_interval=20,
        )

    transient_wrapper = _raw_physx_report([(SOURCE_SHELL, TABLE)])
    _append_transient_raw_occurrence(transient_wrapper, LEFT_PAD, SOURCE_WRAPPER)
    transient_envelope = build_g2_immediate_report_envelope(
        transient_wrapper,
        execution_context=context,
        phase="CLOSE",
        interval_index=2,
        substep_slot=1,
        substeps_per_interval=20,
    )
    with pytest.raises(ValueError, match="real_pbd_g2_classification_coverage_invalid"):
        build_g2_classification_receipt(
            immediate_report_envelope=transient_envelope,
            classification=_classification(
                [_pair_record(SOURCE_SHELL, TABLE, contact_class="BACKGROUND")]
            ),
        )

    classified_transient = build_g2_classification_receipt(
        immediate_report_envelope=transient_envelope,
        classification=_classification(
            [
                _pair_record(SOURCE_SHELL, TABLE, contact_class="BACKGROUND"),
                _pair_record(
                    LEFT_PAD,
                    SOURCE_WRAPPER,
                    contact_class="PROHIBITED_CONTACT",
                    current=False,
                    transient=True,
                ),
            ]
        ),
    )
    transient_sensors = build_g2_sensor_pair_receipt(
        immediate_report_envelope=transient_envelope,
        normalized_sensor_contacts=[],
    )
    transient_source = build_g2_source_state_receipt(
        execution_context=context,
        physics_step=10,
        interval_index=2,
        substep_slot=1,
        phase="CLOSE",
        pre=_source_state_receipt(10)["pre"],
        post=_source_state_receipt(10)["post"],
    )
    transient_result = evaluate_g2_substep(
        execution_context=context,
        immediate_report_envelope=transient_envelope,
        classification_receipt=classified_transient,
        sensor_receipt=transient_sensors,
        source_state_receipt=transient_source,
        action_receipt=_sealed_g2_action_receipt(context, transient_envelope),
    )
    assert transient_result["terminal_kind"] == "PHYSICAL_CONTACT_FAILURE"
    assert "wrapper_or_particle_contact" in transient_result["physical_failures"]

    raw_fragment_forgery = _raw_physx_report([(SOURCE_SHELL, TABLE)])
    raw_fragment_forgery["occurrences"][0]["fragments"][0]["header"][
        "collider1"
    ] = SOURCE_WRAPPER
    with pytest.raises(ValueError, match="real_pbd_g2_immediate_report_invalid"):
        build_g2_immediate_report_envelope(
            raw_fragment_forgery,
            execution_context=context,
            phase="CLOSE",
            interval_index=2,
            substep_slot=1,
            substeps_per_interval=20,
        )

    forged = copy.deepcopy(envelope)
    forged["current_pairs"] = []
    forged["evidence_sha256"] = canonical_json_sha256(
        {key: value for key, value in forged.items() if key != "evidence_sha256"}
    )
    with pytest.raises(ValueError, match="real_pbd_g2_immediate_report_invalid"):
        build_g2_classification_receipt(
            immediate_report_envelope=forged,
            classification=_classification(
                [_pair_record(SOURCE_SHELL, TABLE, contact_class="BACKGROUND")]
            ),
        )


def _source_state_receipt(physics_step: int = 10) -> dict:
    state = {
        "com_position_m": [0.295, 0.075, 0.8233382266115852],
        "orientation_wxyz": [1.0, 0.0, 0.0, 0.0],
        "linear_velocity_m_s": [0.0, 0.0, 0.0],
        "angular_velocity_rad_s": [0.0, 0.0, 0.0],
    }
    return {
        "physics_step": physics_step,
        "pre": state,
        "post": copy.deepcopy(state),
    }


def _action_receipt(phase: str = "CLOSE") -> dict:
    return {
        "authority": "controlled_action_applied_receipt_v1",
        "phase": phase,
        "semantic_action_kind": (
            "GRIPPER_CLOSE" if phase == "CLOSE" else "GRIPPER_CONTACT_SETTLE"
        ),
        "action_sha256": _sha("a"),
        "target_token_sha256": _sha("b"),
        "physics_steps_before_receipt": 0,
    }


def _g2_substep(
    *,
    pairs: list[tuple[str, str]],
    records: list[dict],
    sensor_pairs: list[tuple[str, str]],
    phase: str = "CLOSE",
    physics_step: int = 10,
) -> dict:
    context, _ = _sealed_g2_context()
    raw = _raw_physx_report(pairs, physics_step=physics_step)
    for record in records:
        if record["transient"] and not record["current"]:
            first, second = record["pair"]["collider_paths"]
            _append_transient_raw_occurrence(raw, first, second)
    envelope = build_g2_immediate_report_envelope(
        raw,
        execution_context=context,
        phase=phase,
        interval_index=2,
        substep_slot=1,
        substeps_per_interval=20,
    )
    classification = build_g2_classification_receipt(
        immediate_report_envelope=envelope,
        classification=_classification(records, phase=phase, physics_step=physics_step),
    )
    sensors = build_g2_sensor_pair_receipt(
        immediate_report_envelope=envelope,
        normalized_sensor_contacts=[
            {
                "physics_step": physics_step,
                "collider0_path": first,
                "collider1_path": second,
            }
            for first, second in sensor_pairs
        ],
    )
    source = _source_state_receipt(physics_step)
    source_state = build_g2_source_state_receipt(
        execution_context=context,
        physics_step=physics_step,
        interval_index=2,
        substep_slot=1,
        phase=phase,
        pre=source["pre"],
        post=source["post"],
    )
    return evaluate_g2_substep(
        execution_context=context,
        immediate_report_envelope=envelope,
        classification_receipt=classification,
        sensor_receipt=sensors,
        source_state_receipt=source_state,
        action_receipt=_sealed_g2_action_receipt(context, envelope, phase=phase),
    )


def test_g2_uses_immediate_contact_as_authority_and_requires_exact_sensor_match():
    pairs = [(SOURCE_SHELL, TABLE), (LEFT_PAD, SOURCE_SHELL), (RIGHT_PAD, SOURCE_SHELL)]
    records = [
        _pair_record(SOURCE_SHELL, TABLE, contact_class="BACKGROUND"),
        _pair_record(
            LEFT_PAD,
            SOURCE_SHELL,
            contact_class="INTENDED_CLOSE_CONTACT",
            side="left",
        ),
        _pair_record(
            RIGHT_PAD,
            SOURCE_SHELL,
            contact_class="INTENDED_CLOSE_CONTACT",
            side="right",
        ),
    ]

    result = _g2_substep(
        pairs=pairs,
        records=records,
        sensor_pairs=[(LEFT_PAD, SOURCE_SHELL), (RIGHT_PAD, SOURCE_SHELL)],
    )

    assert result["terminal_kind"] is None
    assert result["current_intended_sides"] == ["left", "right"]
    assert result["next_action_allowed"] is True

    disagreement = _g2_substep(
        pairs=pairs,
        records=records,
        sensor_pairs=[(LEFT_PAD, SOURCE_SHELL)],
    )
    assert disagreement["terminal_kind"] == "PROTOCOL_FAILURE"
    assert disagreement["next_action_allowed"] is False
    assert disagreement["lift_allowed"] is False
    assert disagreement["pour_allowed"] is False


def test_g2_execution_context_rederives_the_trajectory_and_particle_role():
    context, _ = _sealed_g2_context()
    altered_trajectory = copy.deepcopy(context["trajectory"])
    altered_trajectory["actions"][0]["target_token_sha256"] = _sha("f")
    altered_trajectory["trajectory_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in altered_trajectory.items()
            if key != "trajectory_sha256"
        }
    )
    with pytest.raises(ValueError, match="real_pbd_g2_trajectory_binding_invalid"):
        build_g2_execution_context(
            run_id=context["run_id"],
            reset_epoch=context["reset_epoch"],
            g0_certificate=context["g0_certificate"],
            g0_decision=context["g0_decision"],
            trajectory=altered_trajectory,
            baseline_receipt=context["baseline_receipt"],
        )

    altered_baseline = copy.deepcopy(context["baseline_receipt"])
    altered_baseline["particle_collider_paths"] = ["/World/decoyParticles"]
    altered_baseline["evidence_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in altered_baseline.items()
            if key != "evidence_sha256"
        }
    )
    with pytest.raises(ValueError, match="real_pbd_g2_execution_context_binding_invalid"):
        build_g2_execution_context(
            run_id=context["run_id"],
            reset_epoch=context["reset_epoch"],
            g0_certificate=context["g0_certificate"],
            g0_decision=context["g0_decision"],
            trajectory=context["trajectory"],
            baseline_receipt=altered_baseline,
        )


def test_g2_runtime_adapters_preserve_full_physx_evidence_and_same_step_sensors():
    context, _ = _sealed_g2_context()
    raw = _raw_physx_report([(SOURCE_SHELL, TABLE), (LEFT_PAD, SOURCE_SHELL)])
    raw["immediate_read_index"] = 3
    raw["immediate_read_count"] = 4
    envelope = build_g2_immediate_report_envelope(
        raw,
        execution_context=context,
        phase="CLOSE",
        interval_index=2,
        substep_slot=1,
        substeps_per_interval=20,
    )
    assert envelope["authority"] == "real_pbd_g2_immediate_report_envelope_v1"
    assert envelope["current_pairs"] == raw["current_pairs"]
    assert envelope["raw_physx_report"] == raw
    assert envelope["raw_physx_report_sha256"] == canonical_json_sha256(raw)

    sensors = build_g2_sensor_pair_receipt(
        immediate_report_envelope=envelope,
        normalized_sensor_contacts=[
            {
                "physics_step": 10,
                "collider0_path": LEFT_PAD,
                "collider1_path": SOURCE_SHELL,
            },
            {
                "physics_step": 10,
                "collider0_path": LEFT_PAD,
                "collider1_path": SOURCE_SHELL,
            },
        ],
    )
    assert sensors["pairs"] == [[LEFT_PAD, SOURCE_SHELL]]

    malformed = copy.deepcopy(raw)
    malformed["occurrence_count"] = 1
    with pytest.raises(ValueError, match="real_pbd_g2_immediate_report_invalid"):
        build_g2_immediate_report_envelope(
            malformed,
            execution_context=context,
            phase="CLOSE",
            interval_index=2,
            substep_slot=1,
            substeps_per_interval=20,
        )

    multi_fragment = _raw_physx_report([(SOURCE_SHELL, TABLE)])
    duplicate_header = copy.deepcopy(multi_fragment["raw_headers"][0])
    multi_fragment["raw_headers"].append(duplicate_header)
    multi_fragment["header_count"] = 2
    multi_fragment["occurrences"][0]["headers"].append(
        copy.deepcopy(duplicate_header)
    )
    multi_fragment["occurrences"][0]["fragments"].append(
        {
            "header": copy.deepcopy(duplicate_header),
            "contact_data": [],
            "friction_anchors": [],
        }
    )
    duplicate_envelope = build_g2_immediate_report_envelope(
        multi_fragment,
        execution_context=context,
        phase="CLOSE",
        interval_index=2,
        substep_slot=1,
        substeps_per_interval=20,
    )
    assert duplicate_envelope["raw_physx_report"]["occurrences"][0][
        "event_sequence"
    ] == "PERSIST"

    buffered_contact = _raw_physx_report([(SOURCE_SHELL, TABLE)])
    contact = {"position": [0.3, 0.0, 0.8]}
    buffered_contact["raw_contact_data"] = [copy.deepcopy(contact)]
    buffered_contact["contact_data_count"] = 1
    buffered_contact["raw_headers"][0]["num_contact_data"] = 1
    buffered_contact["occurrences"][0]["headers"][0]["num_contact_data"] = 1
    buffered_contact["occurrences"][0]["contact_data"] = [copy.deepcopy(contact)]
    buffered_contact["occurrences"][0]["fragments"][0]["header"][
        "num_contact_data"
    ] = 1
    buffered_contact["occurrences"][0]["fragments"][0]["contact_data"] = [
        copy.deepcopy(contact)
    ]
    build_g2_immediate_report_envelope(
        buffered_contact,
        execution_context=context,
        phase="CLOSE",
        interval_index=2,
        substep_slot=1,
        substeps_per_interval=20,
    )
    buffered_contact["raw_contact_data"][0]["position"][0] = 9.0
    with pytest.raises(ValueError, match="real_pbd_g2_immediate_report_invalid"):
        build_g2_immediate_report_envelope(
            buffered_contact,
            execution_context=context,
            phase="CLOSE",
            interval_index=2,
            substep_slot=1,
            substeps_per_interval=20,
        )


def test_g2_rejects_changed_baseline_wrapper_scope_and_transient_contact():
    changed_baseline = _g2_substep(
        pairs=[(SOURCE_SHELL, "/World/shelf/collision")],
        records=[
            _pair_record(
                SOURCE_SHELL,
                "/World/shelf/collision",
                contact_class="BACKGROUND",
            )
        ],
        sensor_pairs=[],
    )
    assert changed_baseline["terminal_kind"] == "PHYSICAL_CONTACT_FAILURE"

    wrapper_contact = _g2_substep(
        pairs=[(SOURCE_SHELL, TABLE), (LEFT_PAD, SOURCE_WRAPPER)],
        records=[
            _pair_record(SOURCE_SHELL, TABLE, contact_class="BACKGROUND"),
            _pair_record(
                LEFT_PAD,
                SOURCE_WRAPPER,
                contact_class="INTENDED_CLOSE_CONTACT",
                side="left",
            ),
        ],
        sensor_pairs=[(LEFT_PAD, SOURCE_WRAPPER)],
    )
    assert wrapper_contact["terminal_kind"] == "PHYSICAL_CONTACT_FAILURE"

    transient = _g2_substep(
        pairs=[(SOURCE_SHELL, TABLE)],
        records=[
            _pair_record(SOURCE_SHELL, TABLE, contact_class="BACKGROUND"),
            _pair_record(
                LEFT_PAD,
                SOURCE_SHELL,
                contact_class="INTENDED_CLOSE_CONTACT",
                side="left",
                current=False,
                transient=True,
            ),
        ],
        sensor_pairs=[],
    )
    assert transient["terminal_kind"] == "PHYSICAL_CONTACT_FAILURE"

    transient_hand = _g2_substep(
        pairs=[(SOURCE_SHELL, TABLE)],
        records=[
            _pair_record(SOURCE_SHELL, TABLE, contact_class="BACKGROUND"),
            _pair_record(
                HAND,
                SOURCE_SHELL,
                contact_class="PROHIBITED_CONTACT",
                current=False,
                transient=True,
            ),
        ],
        sensor_pairs=[],
    )
    assert transient_hand["terminal_kind"] == "PHYSICAL_CONTACT_FAILURE"
    assert "unexpected_observed_pair" in transient_hand["physical_failures"]


def test_g2_bilateral_certificate_cannot_authorize_lift_or_pour():
    context, _ = _sealed_g2_context()
    gate = G2BilateralCertificate(
        execution_context=context,
    )
    pairs = [(SOURCE_SHELL, TABLE), (LEFT_PAD, SOURCE_SHELL), (RIGHT_PAD, SOURCE_SHELL)]
    records = [
        _pair_record(SOURCE_SHELL, TABLE, contact_class="BACKGROUND"),
        _pair_record(
            LEFT_PAD,
            SOURCE_SHELL,
            contact_class="INTENDED_CLOSE_CONTACT",
            side="left",
        ),
        _pair_record(
            RIGHT_PAD,
            SOURCE_SHELL,
            contact_class="INTENDED_CLOSE_CONTACT",
            side="right",
        ),
    ]
    first = gate.observe(
        _g2_substep(
            pairs=pairs,
            records=records,
            sensor_pairs=[(LEFT_PAD, SOURCE_SHELL), (RIGHT_PAD, SOURCE_SHELL)],
        )
    )
    second = gate.observe(
        _g2_substep(
            pairs=pairs,
            records=records,
            sensor_pairs=[(LEFT_PAD, SOURCE_SHELL), (RIGHT_PAD, SOURCE_SHELL)],
            physics_step=11,
        )
    )

    assert first["certified"] is False
    assert second["certified"] is True
    assert second["lift_allowed"] is False
    assert second["pour_allowed"] is False

    one_sided = gate.observe(
        _g2_substep(
            pairs=[(SOURCE_SHELL, TABLE), (LEFT_PAD, SOURCE_SHELL)],
            records=[
                _pair_record(SOURCE_SHELL, TABLE, contact_class="BACKGROUND"),
                _pair_record(
                    LEFT_PAD,
                    SOURCE_SHELL,
                    contact_class="INTENDED_CLOSE_CONTACT",
                    side="left",
                ),
            ],
            sensor_pairs=[(LEFT_PAD, SOURCE_SHELL)],
            physics_step=12,
        )
    )
    assert one_sided["terminal_kind"] == "PHYSICAL_CONTACT_FAILURE"
    assert one_sided["certified"] is False


def test_g2_trajectory_binds_the_live_pbd_pose_and_has_no_lift_or_frozen_input():
    candidate = {
        "authority": "real_pbd_g0_candidate_v1",
        "id": "top_down_candidate_01",
        "source_frame_grasp_offset_m": [0.001, 0.0, 0.01],
        "approach_direction_world": [0.0, 0.0, -1.0],
        "pregrasp_distance_m": 0.08,
        "insert_distance_m": 0.02,
        "tool_orientation_wxyz": [0.0, 0.0, 1.0, 0.0],
        "control_target_offset_world_m": [0.0, 0.0, -0.0034],
        "finger_joint_indices": [7, 8],
        "close_endpoint_m": 0.028,
        "close_speed_m_s": 0.002,
    }
    source_pose = {
        "position_world_m": [0.295, 0.075, 0.8233382266115852],
        "orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
    }

    trajectory = build_g2_trajectory_spec(
        candidate=candidate,
        live_source_pose=source_pose,
    )

    assert trajectory["new_action_trace_required"] is True
    assert trajectory["frozen_trace_input_allowed"] is False
    assert trajectory["grasp_position_world_m"] == pytest.approx(
        [0.296, 0.075, 0.8333382266115852]
    )
    assert [entry["phase"] for entry in trajectory["actions"]] == [
        "PREGRASP",
        "ALIGN",
        "INSERT",
        "SETTLE",
        "PRECONTACT_SETTLE",
        "CLOSE",
        "CONTACT_SETTLE",
    ]
    assert all(entry["phase"] not in {"LIFT", "HOLD", "POUR"} for entry in trajectory["actions"])

    moved_pose = copy.deepcopy(source_pose)
    moved_pose["position_world_m"][0] += 0.01
    moved = build_g2_trajectory_spec(candidate=candidate, live_source_pose=moved_pose)
    assert moved["source_pose_sha256"] != trajectory["source_pose_sha256"]
    assert moved["grasp_position_world_m"][0] == pytest.approx(
        trajectory["grasp_position_world_m"][0] + 0.01
    )

    frozen = {**candidate, "source_transition_index": 229}
    with pytest.raises(ValueError, match="real_pbd_g2_candidate_provenance_invalid"):
        build_g2_trajectory_spec(candidate=frozen, live_source_pose=source_pose)


def _stage_bytes(
    stage: str,
    decision: str,
    predecessors: dict[str, bytes],
    *,
    run_suffix: str = "",
) -> bytes:
    fixture_identity = canonical_json_sha256(
        {
            "usd_dependency_closure_sha256": _sha("a"),
            "composed_collision_inventory_sha256": _sha("b"),
        }
    )
    if stage == "G0":
        source = {
            "authority": "real_pbd_g0_clearance_decision_v1",
            "decision": decision,
            "checks": {"composed_fixture_complete": decision == "G0_GO"},
            "selected_candidate_id": "candidate",
            "selected_candidate_sha256": _sha("c"),
            "fixture_identity": {
                "usd_dependency_closure_sha256": _sha("a"),
                "composed_collision_inventory_sha256": _sha("b"),
            },
            "certificate_sha256": _sha("d"),
            "g3_g4_filled_load_authorized": False,
        }
    elif stage in {"G1-D", "G1-F"}:
        source = {
            "authority": "real_pbd_g1_treatment_decision_v1",
            "treatment": "dry" if stage == "G1-D" else "filled",
            "decision": decision,
            "fixture_identity_sha256": fixture_identity,
            "fixture_lineage_sha256": fixture_identity,
            "checks": {"trace_bounds": decision.endswith("_GO")},
            "g2_eligible": decision.endswith("_GO"),
            "g3_g4_filled_load_authorized": False,
        }
    elif stage == "G1-COMPARE":
        source = {
            "authority": "real_pbd_g1_baseline_comparison_v1",
            "decision": decision,
            "fixture_identity_sha256": fixture_identity,
            "fixture_lineage_sha256": fixture_identity,
            "checks": {"same_fixture_identity": decision == "G1_GO"},
            "g2_f_authorized": decision == "G1_GO",
            "g3_g4_filled_load_authorized": False,
        }
    else:
        source = {
            "authority": "real_pbd_g2_stage_decision_v1",
            "decision": decision,
            "execution_context_sha256": _sha("e"),
            "checks": {"bilateral_contact": decision.endswith("_GO")},
        }
    stage_evidence = build_stage_evidence(
        stage=stage,
        decision=decision,
        fixture_identity_sha256=fixture_identity,
        treatment_sha256=_sha("b"),
        source_evidence=_hashed(source, field="sha256"),
    )
    artifact = build_stage_artifact(
        stage=stage,
        decision=decision,
        run_id=f"run-{stage.lower()}{run_suffix}",
        reset_epoch=0,
        fixture_identity_sha256=fixture_identity,
        treatment_sha256=_sha("b"),
        stage_evidence=stage_evidence,
        input_closure_sha256=_sha("d"),
        forbidden_frozen_v6_input_count=0,
        predecessor_byte_hashes={
            name: hashlib.sha256(payload).hexdigest()
            for name, payload in predecessors.items()
        },
    )
    return serialize_stage_artifact(artifact)


def _sealed_parent_chain(*, run_suffix: str = "") -> dict[str, bytes]:
    g0 = _stage_bytes("G0", "G0_GO", {}, run_suffix=run_suffix)
    g1d = _stage_bytes("G1-D", "G1_D_GO", {"G0": g0}, run_suffix=run_suffix)
    g1f = _stage_bytes("G1-F", "G1_F_GO", {"G0": g0}, run_suffix=run_suffix)
    comparison = _stage_bytes(
        "G1-COMPARE",
        "G1_GO",
        {"G1-D": g1d, "G1-F": g1f},
        run_suffix=run_suffix,
    )
    g2d = _stage_bytes(
        "G2-D",
        "G2_D_GO",
        {"G0": g0, "G1-COMPARE": comparison},
        run_suffix=run_suffix,
    )
    return {
        "G0": g0,
        "G1-D": g1d,
        "G1-F": g1f,
        "G1-COMPARE": comparison,
        "G2-D": g2d,
    }


def test_g2f_authorization_binds_the_full_parent_chain_and_is_one_use(tmp_path):
    parents = _sealed_parent_chain()
    authorization = build_g2f_one_use_authorization(
        parent_artifact_bytes=parents,
        successor_treatment_sha256=_sha("e"),
        authorization_id=_sha("f"),
    )

    assert authorization["parent_artifact_byte_hashes"] == {
        name: hashlib.sha256(payload).hexdigest()
        for name, payload in parents.items()
    }
    assert authorization["successor_stage"] == "G2-F"
    launch_manifest = build_g2f_successor_launch_manifest(
        authorization=authorization,
        parent_artifact_bytes=parents,
        successor_run_id="g2f-child-run",
        successor_reset_epoch=0,
    )
    assert consume_g2f_one_use_authorization(
        authorization=authorization,
        parent_artifact_bytes=parents,
        successor_launch_manifest=launch_manifest,
        ledger_directory=tmp_path,
    )["consumed"] is True

    with pytest.raises(ValueError, match="real_pbd_g2f_authorization_already_consumed"):
        consume_g2f_one_use_authorization(
            authorization=authorization,
            parent_artifact_bytes=parents,
            successor_launch_manifest=launch_manifest,
            ledger_directory=tmp_path,
        )

    same_parent_different_id = build_g2f_one_use_authorization(
        parent_artifact_bytes=parents,
        successor_treatment_sha256=_sha("e"),
        authorization_id=_sha("a"),
    )
    assert same_parent_different_id["ledger_key_sha256"] == authorization[
        "ledger_key_sha256"
    ]
    with pytest.raises(ValueError, match="real_pbd_g2f_authorization_already_consumed"):
        consume_g2f_one_use_authorization(
            authorization=same_parent_different_id,
            parent_artifact_bytes=parents,
            successor_launch_manifest=build_g2f_successor_launch_manifest(
                authorization=same_parent_different_id,
                parent_artifact_bytes=parents,
                successor_run_id="g2f-child-run",
                successor_reset_epoch=0,
            ),
            ledger_directory=tmp_path,
        )


def test_g2f_consumption_revalidates_parent_bytes_before_burning_the_ledger(tmp_path):
    parents = _sealed_parent_chain()
    authorization = build_g2f_one_use_authorization(
        parent_artifact_bytes=parents,
        successor_treatment_sha256=_sha("e"),
        authorization_id=_sha("f"),
    )
    launch_manifest = build_g2f_successor_launch_manifest(
        authorization=authorization,
        parent_artifact_bytes=parents,
        successor_run_id="g2f-child-run",
        successor_reset_epoch=0,
    )

    with pytest.raises(ValueError, match="real_pbd_g2f_parent_artifact_binding_invalid"):
        consume_g2f_one_use_authorization(
            authorization=authorization,
            parent_artifact_bytes=_sealed_parent_chain(run_suffix="-swapped"),
            successor_launch_manifest=launch_manifest,
            ledger_directory=tmp_path,
        )
    assert list(tmp_path.iterdir()) == []


def test_g2f_stage_artifact_requires_the_consumed_launch_binding(tmp_path):
    parents = _sealed_parent_chain()
    authorization = build_g2f_one_use_authorization(
        parent_artifact_bytes=parents,
        successor_treatment_sha256=_sha("e"),
        authorization_id=_sha("f"),
    )
    manifest = build_g2f_successor_launch_manifest(
        authorization=authorization,
        parent_artifact_bytes=parents,
        successor_run_id="g2f-child-run",
        successor_reset_epoch=0,
    )
    consumption = consume_g2f_one_use_authorization(
        authorization=authorization,
        parent_artifact_bytes=parents,
        successor_launch_manifest=manifest,
        ledger_directory=tmp_path,
    )
    binding = build_g2f_launch_binding(
        authorization=authorization,
        parent_artifact_bytes=parents,
        successor_launch_manifest=manifest,
        consumption_receipt=consumption,
    )
    forged_consumption = copy.deepcopy(consumption)
    forged_consumption["ledger_path"] = str(tmp_path / "missing-ledger.json")
    forged_consumption["sha256"] = canonical_json_sha256(
        {key: value for key, value in forged_consumption.items() if key != "sha256"}
    )
    with pytest.raises(ValueError, match="real_pbd_g2f_consumption_receipt_ledger_missing"):
        build_g2f_launch_binding(
            authorization=authorization,
            parent_artifact_bytes=parents,
            successor_launch_manifest=manifest,
            consumption_receipt=forged_consumption,
        )
    stage_evidence = build_stage_evidence(
        stage="G2-F",
        decision="G2_F_GO",
        fixture_identity_sha256=authorization["fixture_identity_sha256"],
        treatment_sha256=authorization["successor_treatment_sha256"],
        source_evidence=_hashed(
            {
                "authority": "real_pbd_g2_stage_decision_v1",
                "decision": "G2_F_GO",
                "execution_context_sha256": _sha("a"),
                "checks": {"bilateral_contact": True},
            },
            field="sha256",
        ),
    )

    artifact = build_stage_artifact(
        stage="G2-F",
        decision="G2_F_GO",
        run_id="g2f-child-run",
        reset_epoch=0,
        fixture_identity_sha256=authorization["fixture_identity_sha256"],
        treatment_sha256=authorization["successor_treatment_sha256"],
        stage_evidence=stage_evidence,
        input_closure_sha256=_sha("d"),
        forbidden_frozen_v6_input_count=0,
        predecessor_byte_hashes={
            name: hashlib.sha256(parents[name]).hexdigest()
            for name in ("G0", "G1-COMPARE", "G2-D")
        },
        g2f_launch_binding=binding,
    )

    assert serialize_stage_artifact(artifact).endswith(b"\n")


def test_g2f_authorization_rejects_broken_parent_lineage_and_frozen_inputs():
    parents = _sealed_parent_chain()
    broken_g2d = _stage_bytes(
        "G2-D",
        "G2_D_GO",
        {"G0": parents["G0"], "G1-COMPARE": parents["G1-D"]},
    )
    broken = {**parents, "G2-D": broken_g2d}

    with pytest.raises(ValueError, match="real_pbd_g2f_parent_lineage_invalid"):
        build_g2f_one_use_authorization(
            parent_artifact_bytes=broken,
            successor_treatment_sha256=_sha("e"),
            authorization_id=_sha("f"),
        )

    with pytest.raises(ValueError, match="real_pbd_stage_frozen_input_invalid"):
        build_stage_artifact(
            stage="G0",
            decision="G0_GO",
            run_id="run-g0",
            reset_epoch=0,
            fixture_identity_sha256=_sha("a"),
            treatment_sha256=_sha("b"),
            stage_evidence=json.loads(
                _stage_bytes("G0", "G0_GO", {}).decode("utf-8")
            )["stage_evidence"],
            input_closure_sha256=_sha("d"),
            forbidden_frozen_v6_input_count=1,
            predecessor_byte_hashes={},
        )


def test_rejected_stage_artifacts_remain_sealed_but_can_never_authorize_g2f():
    rejected_g0 = _stage_bytes("G0", "G0_NO_GO", {})
    parents = _sealed_parent_chain()
    rejected_chain = {**parents, "G0": rejected_g0}

    with pytest.raises(ValueError, match="real_pbd_g2f_parent_lineage_invalid"):
        build_g2f_one_use_authorization(
            parent_artifact_bytes=rejected_chain,
            successor_treatment_sha256=_sha("e"),
            authorization_id=_sha("f"),
        )


def test_stage_artifact_cannot_relabel_typed_no_go_evidence_as_go():
    no_go_evidence = json.loads(
        _stage_bytes("G0", "G0_NO_GO", {}).decode("utf-8")
    )["stage_evidence"]

    with pytest.raises(ValueError, match="real_pbd_stage_artifact_evidence_binding_invalid"):
        build_stage_artifact(
            stage="G0",
            decision="G0_GO",
            run_id="relabel-attempt",
            reset_epoch=0,
            fixture_identity_sha256=no_go_evidence["fixture_identity_sha256"],
            treatment_sha256=no_go_evidence["treatment_sha256"],
            stage_evidence=no_go_evidence,
            input_closure_sha256=_sha("c"),
            forbidden_frozen_v6_input_count=0,
            predecessor_byte_hashes={},
        )

    static_evaluation = _hashed(
        {
            "authority": "real_pbd_static_fixture_preflight_v1",
            "fixture_identity_sha256": _sha("a"),
            "g0_decision": "G0_GO",
        },
        field="sha256",
    )
    static_report = {
        "authority": "real_pbd_static_fixture_preflight_report_v1",
        "asset_sha256": _sha("b"),
        "usd_dependency_closure_sha256": _sha("a"),
        "evaluation": static_evaluation,
    }
    with pytest.raises(ValueError, match="real_pbd_stage_source_evidence_binding_invalid"):
        build_stage_evidence(
            stage="G0",
            decision="G0_GO",
            fixture_identity_sha256=_sha("a"),
            treatment_sha256=_sha("a"),
            source_evidence={
                **static_report,
                "report_sha256": canonical_json_sha256(static_report),
            },
        )

    empty_g1_checks = {
        "authority": "real_pbd_g1_treatment_decision_v1",
        "treatment": "dry",
        "decision": "G1_D_GO",
        "fixture_identity_sha256": _sha("a"),
        "fixture_lineage_sha256": _sha("a"),
        "checks": {},
        "g2_eligible": True,
        "g3_g4_filled_load_authorized": False,
    }
    with pytest.raises(ValueError, match="real_pbd_stage_source_evidence_binding_invalid"):
        build_stage_evidence(
            stage="G1-D",
            decision="G1_D_GO",
            fixture_identity_sha256=_sha("a"),
            treatment_sha256=_sha("b"),
            source_evidence=_hashed(empty_g1_checks, field="sha256"),
        )


def test_static_fixture_preflight_reports_current_zero_mass_as_a_hard_no_go():
    result = evaluate_static_pbd_fixture_preflight(
        fixture={
            "fixture_identity_sha256": _sha("a"),
            "source_dry_mass_kg": 0.02,
            "particle_density_kg_m3": 0.0,
            "particle_mass_kg": 0.0,
            "particle_count": 3600,
            "wrapper_collider_count": 145,
            "expected_wrapper_collider_count": 145,
            "runtime_cooked_geometry_available": False,
            "runtime_stable_particle_ids_available": False,
        }
    )

    assert result["g0_decision"] == "G0_NO_GO"
    assert result["g2_f_prerequisites_ready"] is False
    assert result["g3_g4_filled_load_authorized"] is False
    assert "authored_particle_mass_and_density_nonpositive" in result[
        "no_go_reasons"
    ]
    assert "runtime_cooked_geometry_required" in result["no_go_reasons"]


def _source_stage_snapshot(*, collision_filter_sha256: str = _sha("f")) -> dict:
    return build_source_stage_authoring_snapshot(
        source_actor_path="/World/beaker2",
        source_prim_type="Xform",
        source_reference_sha256=_sha("a"),
        source_transform_authored_sha256=_sha("b"),
        source_velocity_authored_sha256=_sha("c"),
        source_kinematic_enabled=False,
        source_collision_filter_sha256=collision_filter_sha256,
        source_collision_api_sha256=_sha("d"),
        source_attachment_constraint_paths=[],
        source_collider_inventory_sha256=_sha("e"),
    )


def test_source_stage_authoring_diff_rejects_hidden_filter_or_attachment_mutation():
    before = _source_stage_snapshot()
    unchanged = evaluate_source_stage_authoring_diff(before=before, after=before)
    assert unchanged["valid"] is True
    assert unchanged["changed_fields"] == []

    changed = _source_stage_snapshot(collision_filter_sha256=_sha("a"))
    mutation = evaluate_source_stage_authoring_diff(before=before, after=changed)
    assert mutation["valid"] is False
    assert mutation["changed_fields"] == ["source_collision_filter_sha256"]


def test_particle_identity_tracker_requires_real_complete_ids_not_array_order():
    tracker = ParticleRuntimeIdentityTracker(expected_particle_ids=[17, 3, 9])
    first = tracker.observe(
        physics_step=20,
        particle_ids=[9, 17, 3],
        positions_world_m=[[0.3, 0.0, 0.8], [0.1, 0.0, 0.8], [0.2, 0.0, 0.8]],
        source_frame_pose_sha256=_sha("a"),
    )
    second = tracker.observe(
        physics_step=21,
        particle_ids=[3, 9, 17],
        positions_world_m=[[0.2, 0.0, 0.8], [0.3, 0.0, 0.8], [0.1, 0.0, 0.8]],
        source_frame_pose_sha256=_sha("b"),
    )

    assert first["coverage_complete"] is True
    assert second["coverage_complete"] is True
    assert first["stable_ids_sha256"] == second["stable_ids_sha256"]
    assert first["canonical_positions_by_id_sha256"] == second[
        "canonical_positions_by_id_sha256"
    ]

    with pytest.raises(ValueError, match="real_pbd_g1_particle_ids_invalid"):
        tracker.observe(
            physics_step=22,
            particle_ids=[3, 9],
            positions_world_m=[[0.2, 0.0, 0.8], [0.3, 0.0, 0.8]],
            source_frame_pose_sha256=_sha("c"),
        )
