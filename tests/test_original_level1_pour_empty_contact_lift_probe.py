from __future__ import annotations

import ast
import copy
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

from tools.labutopia_fluid import (
    run_original_level1_pour_empty_contact_lift_probe as probe,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_original_empty_contact_lift_v1.yaml"
)
PRODUCTION_CONFIG_PATH = REPO_ROOT / "config/level1_pour.yaml"
SOURCE = "/World/beaker2/mesh"
SUPPORT = "/World/Cube"
LEFT_BODY = "/World/Franka/panda_leftfinger"
RIGHT_BODY = "/World/Franka/panda_rightfinger"
LEFT_COLLIDER = LEFT_BODY + "/collision"
RIGHT_COLLIDER = RIGHT_BODY + "/collision"


def _components(**changes):
    value = {
        "runtime_error": False,
        "protocol_no_go": False,
        "contact_report_perturbation": False,
        "original_contact_lift_passed": True,
        "retention_continuation_passed": True,
        "zero_friction_causality_passed": True,
    }
    value.update(changes)
    return value


def _header(
    event_type: str,
    *,
    collider0: str,
    collider1: str,
    actor0: str,
    actor1: str,
    contact_offset: int = 0,
    contact_count: int = 1,
    friction_offset: int = 0,
    friction_count: int = 0,
):
    return {
        "type": event_type,
        "stage_id": 7,
        "actor0": actor0,
        "actor1": actor1,
        "collider0": collider0,
        "collider1": collider1,
        "proto_index0": 0xFFFFFFFF,
        "proto_index1": 0xFFFFFFFF,
        "contact_data_offset": contact_offset,
        "num_contact_data": contact_count,
        "friction_anchors_offset": friction_offset,
        "num_friction_anchors_data": friction_count,
    }


def _bound(path, low, high):
    return {
        "path": path,
        "range_min_m": list(low),
        "range_max_m": list(high),
        "bbox_matrix": np.eye(4).tolist(),
        "parent_world_matrix": np.eye(4).tolist(),
    }


def _geometry_fixture():
    return {
        "gravity_world_m_s2": [0.0, 0.0, -9.81],
        "source": _bound(SOURCE, (-1.0, -1.0, 0.0), (1.0, 1.0, 10.0)),
        "finger_colliders": {
            LEFT_COLLIDER: _bound(
                LEFT_COLLIDER,
                (-2.0, -0.5, 1.0),
                (-1.0, 0.5, 9.0),
            ),
            RIGHT_COLLIDER: _bound(
                RIGHT_COLLIDER,
                (1.0, -0.5, 1.0),
                (2.0, 0.5, 9.0),
            ),
        },
        "target_pairs": [
            {
                "side": "left",
                "finger_body": LEFT_BODY,
                "finger_collider": LEFT_COLLIDER,
                "source_collider": SOURCE,
            },
            {
                "side": "right",
                "finger_body": RIGHT_BODY,
                "finger_collider": RIGHT_COLLIDER,
                "source_collider": SOURCE,
            },
        ],
    }


def _qualified_occurrences():
    return [
        {
            "source_collider": SOURCE,
            "finger_collider": LEFT_COLLIDER,
            "current": True,
            "points": [
                {
                    "position_world_m": [-1.0, 0.0, 2.0],
                    "source_normal_world": [1.0, 0.0, 0.0],
                }
            ],
        },
        {
            "source_collider": SOURCE,
            "finger_collider": RIGHT_COLLIDER,
            "current": True,
            "points": [
                {
                    "position_world_m": [1.0, 0.0, 8.0],
                    "source_normal_world": [-1.0, 0.0, 0.0],
                }
            ],
        },
    ]


def _state(z, *, support=True, linear_speed=0.0, angular_speed_degrees=0.0):
    return {
        "source_com_m": [0.0, 0.0, float(z)],
        "source_linear_speed_m_s": float(linear_speed),
        "source_angular_speed_degrees_s": float(angular_speed_degrees),
        "finger_aperture_rate_m_s": 0.0,
        "support_current": bool(support),
    }


def _original_trace():
    post_heights = {
        **{index: 0.0 for index in range(10)},
        10: 0.01,
        11: 0.06,
        12: 0.12,
        13: 0.14,
        14: 0.15,
    }
    records = []
    previous = _state(0.0)
    for index in range(75):
        continuation_index = index - 15 if index >= 15 else None
        post_z = post_heights.get(index, 0.15)
        support = index < 11
        post = _state(post_z, support=support)
        contact = {
            "bilateral_qualified": index >= 10,
            "prohibited_contact": False,
            "source_tool_drift_translation_m": 0.001,
            "source_tool_drift_rotation_degrees": 1.0,
            "left_friction_anchor_norm_n_s": 2.0e-5 if index >= 10 else 0.0,
            "right_friction_anchor_norm_n_s": 2.0e-5 if index >= 10 else 0.0,
            "support_event": (
                "LOST" if index == 11 else "PERSIST" if index < 11 else None
            ),
            "support_contact_count": 0 if index == 11 else 1 if index < 11 else 0,
            "support_friction_anchor_count": 0,
            "support_impulse_n_s": 0.0,
        }
        records.append(
            {
                "transition_index": index,
                "pre": copy.deepcopy(previous),
                "post": post,
                "phase_before": "PICKING",
                "phase_after": "POURING" if index >= 14 else "PICKING",
                "action_receipt": (
                    {
                        "native_event": 5,
                        "applied": True,
                        "normal_return": True,
                        "apply_count": 1,
                    }
                    if index == 10
                    else None
                ),
                "contact": contact,
                "production_terminal": index == 14,
                "terminal_outcome": "POURING" if index == 14 else None,
                "continuation_index": continuation_index,
                "controller_called": index < 15,
                "new_action_applied": index == 10,
            }
        )
        previous = post
    return records


def _ablation_trace():
    records = _original_trace()
    previous = _state(0.0)
    for record in records:
        index = record["transition_index"]
        z = 0.0 if index < 10 else min(0.019, (index - 9) * 0.002)
        post = _state(z, support=True)
        record["pre"] = copy.deepcopy(previous)
        record["post"] = post
        record["phase_after"] = "PICKING"
        record["contact"].update(
            bilateral_qualified=index >= 10,
            left_friction_anchor_norm_n_s=0.0,
            right_friction_anchor_norm_n_s=0.0,
            support_event="PERSIST",
            support_contact_count=1,
        )
        if index == 14:
            record["terminal_outcome"] = "PICKING_FAILURE"
        previous = post
    return records


def _comparison_summary():
    sample = {
        "controller_event": 4,
        "joint_positions_rad": [0.0] * 9,
        "tool_position_m": [0.0, 0.0, 1.0],
        "tool_orientation_wxyz": [1.0, 0.0, 0.0, 0.0],
        "source_position_m": [0.0, 0.0, 0.8],
        "source_orientation_wxyz": [1.0, 0.0, 0.0, 0.0],
        "tool_linear_velocity_m_s": [0.0, 0.0, 0.0],
        "tool_angular_velocity_rad_s": [0.0, 0.0, 0.0],
        "source_linear_velocity_m_s": [0.0, 0.0, 0.0],
        "source_angular_velocity_rad_s": [0.0, 0.0, 0.0],
        "predicate_margins": {
            "normalized_height_lower": 0.2,
            "inward_cosine": 0.1,
        },
    }
    return {
        "config_sha256": "a" * 64,
        "requested_pose_sha256": "b" * 64,
        "readback_pose_sha256": "c" * 64,
        "reset_count": 2,
        "controller_events": [0, 1, 2, 3, 4, 5, 6],
        "action_sha256": [str(index) * 64 for index in range(1, 8)],
        "controller_outcome": "POURING",
        "samples": [sample],
        "continuation": [copy.deepcopy(sample) for _ in range(60)],
        "continuation_world_indices": list(range(100, 160)),
        "retention_passed": True,
        "common_contact_stream": [["FOUND", SOURCE, LEFT_COLLIDER]],
    }


def _pair_row(pair_id, *, target, static, dynamic, other="01020304"):
    return {
        "pair_id": pair_id,
        "eligible": True,
        "target_pair": target,
        "runtime_authority": "physx_live_solver_material_v1",
        "selected_friction_combine": "multiply",
        "selected_restitution_combine": "max",
        "effective_static_friction": static,
        "effective_dynamic_friction": dynamic,
        "effective_restitution": 0.1,
        "other_solver_terms_float32_hex": other,
    }


def _complete_audit():
    return {
        "coverage": {name: True for name in probe.REQUIRED_AUDIT_SURFACES},
        "post_reset_counts": {
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
        },
        "reset_root_write_count": 1,
        "zero_write_epoch_opened": True,
    }


def test_diagnostic_config_projects_exactly_to_original_production_and_freezes_bytes(
    tmp_path,
):
    frozen = probe.freeze_diagnostic_config(
        CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )
    config = frozen["config"]

    assert frozen["canonical_bytes"].endswith(b"\n")
    assert json.loads(frozen["canonical_bytes"]) == config
    assert len(frozen["sha256"]) == 64
    assert probe.production_visible_projection(config) == (
        probe.production_visible_projection(
            yaml.safe_load(PRODUCTION_CONFIG_PATH.read_text(encoding="utf-8"))
        )
    )
    assert config["usd_path"] == "assets/chemistry_lab/lab_001/lab_001.usd"
    assert "usd_path" not in config["robot"]
    assert config["task"]["max_steps"] == 1500
    assert config["max_episodes"] == 1
    assert config["multi_run"]["run_dir"] == "collector"
    assert config["hydra"]["run"]["dir"] == "hydra"
    assert config["diagnostic"]["treatments"] == list(probe.TREATMENTS)
    assert config["diagnostic"]["numpy_seed"] == 20260717
    assert config["diagnostic"]["physics_dt"] == pytest.approx(1.0 / 60.0)
    assert config["diagnostic"]["gravity_world_m_s2"] == [0.0, 0.0, -9.81]
    assert config["diagnostic"]["retention_steps"] == 60
    assert config["diagnostic"]["child_timeout_seconds"] == 240

    first_dir = tmp_path / "control"
    second_dir = tmp_path / "instrumented"
    first = probe.write_frozen_config(frozen["canonical_bytes"], first_dir)
    second = probe.write_frozen_config(frozen["canonical_bytes"], second_dir)
    assert first.read_bytes() == second.read_bytes() == frozen["canonical_bytes"]
    assert first_dir.stat().st_mode & 0o777 == 0o700
    assert second_dir.stat().st_mode & 0o777 == 0o700


def test_config_projection_rejects_production_drift_or_escaping_output(tmp_path):
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    config["task"]["max_steps"] = 1499
    drifted = tmp_path / "drifted.yaml"
    drifted.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="probe_config_production_projection_mismatch"):
        probe.freeze_diagnostic_config(
            drifted,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )

    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    config["multi_run"]["run_dir"] = str(tmp_path / "escape")
    escaped = tmp_path / "escaped.yaml"
    escaped.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="probe_config_output_route_invalid"):
        probe.freeze_diagnostic_config(
            escaped,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )


def test_parent_module_has_no_top_level_isaac_omni_pxr_or_carb_imports():
    tree = ast.parse(Path(probe.__file__).read_text(encoding="utf-8"))
    imported_roots = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    assert imported_roots.isdisjoint({"isaacsim", "omni", "pxr", "carb"})

    source = Path(probe.__file__).read_text(encoding="utf-8")
    assert "from factories.robot_factory import create_robot" in source
    assert "from factories.task_factory import create_task" in source
    assert "from factories.controller_factory import create_controller" in source
    assert source.index("def _run_runtime_child") < source.index(
        "from factories.robot_factory import create_robot"
    )


def test_child_commands_are_exact_cpu_backend_treatment_commands(tmp_path):
    config = tmp_path / "frozen_config.json"
    treatment_dir = tmp_path / "control"
    command = probe.build_child_command(
        treatment="control",
        frozen_config_path=config,
        treatment_dir=treatment_dir,
        run_nonce="nonce-1",
        parent_pid=1234,
        expected_config_sha256="a" * 64,
        python_executable=sys.executable,
    )
    assert command == [
        str(Path(sys.executable).resolve()),
        str(Path(probe.__file__).resolve()),
        "--runtime-child",
        "--headless",
        "--treatment",
        "control",
        "--frozen-config",
        str(config.resolve()),
        "--out-dir",
        str(treatment_dir.resolve()),
        "--run-nonce",
        "nonce-1",
        "--parent-pid",
        "1234",
        "--expected-config-sha256",
        "a" * 64,
    ]
    assert "gpu" not in command
    assert "--backend" not in command

    with pytest.raises(ValueError, match="probe_treatment_invalid"):
        probe.build_child_command(
            treatment="tuned_friction",
            frozen_config_path=config,
            treatment_dir=treatment_dir,
            run_nonce="nonce-1",
            parent_pid=1234,
            expected_config_sha256="a" * 64,
        )


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({}, "ORIGINAL_EMPTY_BEAKER_FRICTION_CAUSAL_PASS"),
        (
            {"zero_friction_causality_passed": False},
            "ZERO_FRICTION_CAUSALITY_FAIL",
        ),
        (
            {"retention_continuation_passed": False},
            "EMPTY_BEAKER_RETENTION_CONTINUATION_FAIL",
        ),
        (
            {"original_contact_lift_passed": False},
            "ORIGINAL_EMPTY_BEAKER_CONTACT_LIFT_FAIL",
        ),
        (
            {"contact_report_perturbation": True},
            "CONTACT_REPORT_PERTURBATION_NO_GO",
        ),
        ({"protocol_no_go": True}, "PROBE_PROTOCOL_NO_GO"),
        ({"runtime_error": True}, "PROBE_RUNTIME_ERROR"),
        (
            {
                "runtime_error": True,
                "protocol_no_go": True,
                "contact_report_perturbation": True,
                "original_contact_lift_passed": False,
                "retention_continuation_passed": False,
                "zero_friction_causality_passed": False,
            },
            "PROBE_RUNTIME_ERROR",
        ),
    ],
)
def test_decision_precedence_is_fixed(changes, expected):
    assert probe.select_decision(_components(**changes)) == expected


def test_decision_rejects_missing_or_nonboolean_component_authority():
    incomplete = _components()
    del incomplete["protocol_no_go"]
    with pytest.raises(ValueError, match="probe_decision_components_invalid"):
        probe.select_decision(incomplete)

    contradictory = _components(runtime_error=1)
    with pytest.raises(ValueError, match="probe_decision_components_invalid"):
        probe.select_decision(contradictory)


def test_trace_hash_chain_binds_identity_order_terminal_and_strict_jsonl(tmp_path):
    records = []
    for kind, payload in (
        ("bootstrap", {"reset_count": 2}),
        ("transition", {"transition_index": 0}),
        ("terminal", {"outcome": "POURING"}),
    ):
        records.append(
            probe.make_trace_record(
                records,
                treatment="instrumented_original",
                run_nonce="nonce-1",
                parent_pid=111,
                child_pid=222,
                run_id="run-1",
                kind=kind,
                payload=payload,
            )
        )
    path = tmp_path / "trace.jsonl"
    probe.atomic_create_jsonl(path, records)

    loaded = probe.load_strict_jsonl(path)
    validated = probe.validate_trace_records(
        loaded,
        expected_treatment="instrumented_original",
        expected_run_nonce="nonce-1",
        expected_parent_pid=111,
        expected_child_pid=222,
        expected_run_id="run-1",
    )
    assert validated["record_count"] == 3
    assert validated["terminal_index"] == 2
    assert validated["chain_sha256"] == records[-1]["record_sha256"]

    tampered = copy.deepcopy(loaded)
    tampered[1]["payload"]["transition_index"] = 9
    with pytest.raises(ValueError, match="probe_trace_record_hash_mismatch"):
        probe.validate_trace_records(
            tampered,
            expected_treatment="instrumented_original",
            expected_run_nonce="nonce-1",
            expected_parent_pid=111,
            expected_child_pid=222,
            expected_run_id="run-1",
        )

    extra = copy.deepcopy(loaded)
    extra.append(copy.deepcopy(extra[-1]))
    with pytest.raises(ValueError, match="probe_trace_data_after_terminal"):
        probe.validate_trace_records(
            extra,
            expected_treatment="instrumented_original",
            expected_run_nonce="nonce-1",
            expected_parent_pid=111,
            expected_child_pid=222,
            expected_run_id="run-1",
        )


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"{}",
        b"\n",
        b'[{"a":1}]\n',
        b'{"a":1,"a":2}\n',
        b'{"a":NaN}\n',
        b"{}\n\n",
        b"\xff\n",
    ],
)
def test_strict_json_object_rejects_partial_duplicate_nonfinite_or_extra_data(
    tmp_path,
    payload,
):
    path = tmp_path / "artifact.json"
    path.write_bytes(payload)
    with pytest.raises(ValueError, match="probe_strict_json_invalid"):
        probe.load_strict_json_object(path)


def test_create_only_artifacts_never_replace_and_reject_nonfinite(tmp_path):
    path = tmp_path / "report.json"
    probe.atomic_create_json(path, {"finite": 1.0})
    assert json.loads(path.read_text(encoding="utf-8")) == {"finite": 1.0}

    with pytest.raises(FileExistsError, match="probe_output_exists"):
        probe.atomic_create_json(path, {"replacement": True})
    with pytest.raises(ValueError, match="probe_json_nonfinite"):
        probe.atomic_create_json(tmp_path / "nan.json", {"value": np.nan})


def test_canonical_action_binds_channel_order_shape_none_mask_and_float64_bytes():
    action = {
        "joint_positions": [1.0, None, -0.0],
        "joint_velocities": None,
        "joint_efforts": [None, 2.0, 3.0],
    }
    canonical = probe.canonicalize_action(action)

    assert canonical["channel_order"] == list(probe.ACTION_CHANNELS)
    assert canonical["channels"]["joint_positions"]["shape"] == [3]
    assert canonical["channels"]["joint_positions"]["none_mask_hex"] == "02"
    assert canonical["channels"]["joint_velocities"]["present"] is False
    assert len(canonical["sha256"]) == 64
    assert canonical != probe.canonicalize_action(
        {**action, "joint_positions": [1.0, 0.0, -0.0]}
    )

    with pytest.raises(ValueError, match="probe_action_value_invalid"):
        probe.canonicalize_action(
            {**action, "joint_positions": [1.0, np.nan, 0.0]}
        )


def test_action_ledger_requires_none_state_skip_and_exactly_once_next_transition_apply():
    close = probe.canonicalize_action({"joint_positions": [None] * 7 + [0.028, 0.028]})
    lift = probe.canonicalize_action({"joint_positions": [0.1] * 7 + [None, None]})
    records = [
        {
            "transition_index": 0,
            "state_present": False,
            "controller_call_count": 0,
            "native_event": None,
            "action": None,
            "apply_count": 0,
            "integrating_transition_index": None,
            "phase_after": "PICKING",
        },
        {
            "transition_index": 1,
            "state_present": True,
            "controller_call_count": 1,
            "native_event": 4,
            "action": close,
            "apply_count": 1,
            "apply_index": 0,
            "integrating_transition_index": 2,
            "phase_after": "PICKING",
        },
        {
            "transition_index": 2,
            "state_present": True,
            "controller_call_count": 1,
            "native_event": 5,
            "action": lift,
            "apply_count": 1,
            "apply_index": 1,
            "integrating_transition_index": 3,
            "phase_after": "PICKING",
        },
        {
            "transition_index": 3,
            "state_present": True,
            "controller_call_count": 1,
            "native_event": 6,
            "action": None,
            "apply_count": 0,
            "integrating_transition_index": None,
            "phase_after": "POURING",
            "terminal_outcome": "POURING",
        },
    ]
    summary = probe.validate_action_ledger(records, maximum_production_steps=1500)
    assert summary["valid"] is True
    assert summary["close_transition_index"] == 1
    assert summary["lift_command_transition_index"] == 2
    assert summary["k_lift"] == 3
    assert summary["apply_count"] == 2

    called_on_none = copy.deepcopy(records)
    called_on_none[0]["controller_call_count"] = 1
    with pytest.raises(ValueError, match="probe_ledger_controller_called_on_none"):
        probe.validate_action_ledger(
            called_on_none,
            maximum_production_steps=1500,
        )

    duplicate_apply = copy.deepcopy(records)
    duplicate_apply[1]["apply_count"] = 2
    with pytest.raises(ValueError, match="probe_ledger_apply_count_invalid"):
        probe.validate_action_ledger(
            duplicate_apply,
            maximum_production_steps=1500,
        )


def test_contact_reduction_uses_all_fragments_and_pinned_actor_orientation():
    occurrence = {
        "canonical_pair": [
            {"collider_path": LEFT_COLLIDER, "proto_index": 0xFFFFFFFF},
            {"collider_path": SOURCE, "proto_index": 0xFFFFFFFF},
        ],
        "current": True,
        "fragments": [
            {
                "header": _header(
                    "FOUND",
                    collider0=SOURCE,
                    collider1=LEFT_COLLIDER,
                    actor0="/World/beaker2",
                    actor1=LEFT_BODY,
                    contact_offset=0,
                    friction_offset=0,
                    friction_count=1,
                ),
                "contact_data": [
                    {
                        "position": [-1.0, 0.0, 5.0],
                        "normal": [1.0, 0.0, 0.0],
                        "impulse": [-2.0e-4, 0.0, 0.0],
                        "separation": -1.0e-4,
                    }
                ],
                "friction_anchors": [
                    {"position": [-1.0, 0.0, 5.0], "impulse": [0.0, 3.0e-5, 0.0]}
                ],
            },
            {
                "header": _header(
                    "FOUND",
                    collider0=SOURCE,
                    collider1=LEFT_COLLIDER,
                    actor0="/World/beaker2",
                    actor1=LEFT_BODY,
                    contact_offset=1,
                    friction_offset=1,
                    friction_count=1,
                ),
                "contact_data": [
                    {
                        "position": [-1.0, 0.1, 5.0],
                        "normal": [1.0, 0.0, 0.0],
                        "impulse": [-1.0e-4, 0.0, 0.0],
                        "separation": -1.0e-4,
                    }
                ],
                "friction_anchors": [
                    {"position": [-1.0, 0.1, 5.0], "impulse": [0.0, 0.0, 4.0e-5]}
                ],
            },
        ],
    }
    reduced = probe.reduce_contact_occurrence(
        occurrence,
        source_collider=SOURCE,
        impulse_actor="collider0",
        normal_direction="collider0_to_collider1",
    )
    assert len(reduced["points"]) == 2
    assert reduced["normal_impulse_n_s"] == pytest.approx(3.0e-4)
    assert reduced["friction_anchor_norm_n_s"] == pytest.approx(7.0e-5)
    assert reduced["points"][0]["source_normal_world"] == [-1.0, -0.0, -0.0]

    invalid = copy.deepcopy(occurrence)
    invalid["fragments"][0]["contact_data"][0]["impulse"] = [2.0e-4, 0.0, 0.0]
    with pytest.raises(ValueError, match="probe_contact_negative_normal_impulse"):
        probe.reduce_contact_occurrence(
            invalid,
            source_collider=SOURCE,
            impulse_actor="collider0",
            normal_direction="collider0_to_collider1",
        )

    prototype = copy.deepcopy(occurrence)
    prototype["canonical_pair"][0]["proto_index"] = 7
    with pytest.raises(ValueError, match="probe_contact_prototype_unsupported"):
        probe.reduce_contact_occurrence(
            prototype,
            source_collider=SOURCE,
            impulse_actor="collider0",
            normal_direction="collider0_to_collider1",
        )


def test_sealed_bound_transform_is_applied_exactly_once_and_round_trips():
    bbox = np.eye(4)
    bbox[3, :3] = [1.0, 2.0, 3.0]
    parent = np.eye(4)
    parent[3, :3] = [10.0, 20.0, 30.0]
    bound = {
        "path": "/World/collider",
        "range_min_m": [0.0, 0.0, 0.0],
        "range_max_m": [2.0, 4.0, 6.0],
        "bbox_matrix": bbox.tolist(),
        "parent_world_matrix": parent.tolist(),
    }
    transformed = probe.transform_sealed_bound(bound)

    assert transformed["world_corners_m"][0] == [11.0, 22.0, 33.0]
    assert transformed["world_corners_m"][-1] == [13.0, 26.0, 39.0]
    assert transformed["world_center_m"] == [12.0, 24.0, 36.0]
    raw = probe.world_point_to_raw_bound([13.0, 26.0, 39.0], bound)
    assert raw == pytest.approx([2.0, 4.0, 6.0])


def test_bilateral_geometry_accepts_closed_boundaries_and_rejects_every_bad_point():
    result = probe.evaluate_bilateral_geometry(
        _qualified_occurrences(),
        geometry=_geometry_fixture(),
        finger_aperture_rate_m_s=0.01,
    )
    assert result["protocol_valid"] is True
    assert result["qualified"] is True
    assert result["left_point_count"] == 1
    assert result["right_point_count"] == 1
    assert result["points"][0]["margins"]["height_lower"] == pytest.approx(0.0)
    assert result["points"][1]["margins"]["height_upper"] == pytest.approx(0.0)

    edge = _qualified_occurrences()
    edge[0]["points"][0]["position_world_m"][1] = 0.5
    failed = probe.evaluate_bilateral_geometry(
        edge,
        geometry=_geometry_fixture(),
        finger_aperture_rate_m_s=0.0,
    )
    assert failed["protocol_valid"] is True
    assert failed["qualified"] is False
    assert "pad_interior" in failed["failure_reasons"]

    unknown = _qualified_occurrences()
    unknown[0]["finger_collider"] = LEFT_BODY + "/unknown"
    blocked = probe.evaluate_bilateral_geometry(
        unknown,
        geometry=_geometry_fixture(),
        finger_aperture_rate_m_s=0.0,
    )
    assert blocked["protocol_valid"] is False
    assert blocked["qualified"] is False
    assert "unknown_target_pair" in blocked["protocol_failures"]


def test_unique_point_assignment_rejects_absent_ambiguous_or_out_of_tolerance_match():
    matched = probe.unique_minimum_distance_assignment(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        [[1.0005, 0.0, 0.0], [0.0005, 0.0, 0.0]],
        maximum_distance_m=0.001,
    )
    assert matched["assignment"] == [1, 0]
    assert matched["maximum_distance_m"] == pytest.approx(0.0005)

    with pytest.raises(ValueError, match="probe_assignment_not_unique"):
        probe.unique_minimum_distance_assignment(
            [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
            [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
            maximum_distance_m=0.001,
        )
    with pytest.raises(ValueError, match="probe_assignment_distance_exceeded"):
        probe.unique_minimum_distance_assignment(
            [[0.0, 0.0, 0.0]],
            [[0.002, 0.0, 0.0]],
            maximum_distance_m=0.001,
        )


def test_original_trace_uses_exact_lift_loss_rise_and_60_step_retention_boundaries():
    result = probe.evaluate_original_lift_trace(
        _original_trace(),
        physics_dt=1.0 / 60.0,
        retention_steps=60,
        rise_threshold_m=0.12,
    )
    assert result["protocol_valid"] is True
    assert result["k_lift"] == 10
    assert result["k_loss"] == 11
    assert result["k_rise"] == 12
    assert result["airborne_duration_s"] == pytest.approx(2.0 / 60.0)
    assert result["contact_lift_passed"] is True
    assert result["retention_passed"] is True
    assert result["continuation_count"] == 60

    threshold_friction = _original_trace()
    threshold_friction[11]["contact"]["left_friction_anchor_norm_n_s"] = 1.0e-5
    failed = probe.evaluate_original_lift_trace(
        threshold_friction,
        physics_dt=1.0 / 60.0,
        retention_steps=60,
        rise_threshold_m=0.12,
    )
    assert failed["contact_lift_passed"] is False

    short = _original_trace()[:-1]
    short_result = probe.evaluate_original_lift_trace(
        short,
        physics_dt=1.0 / 60.0,
        retention_steps=60,
        rise_threshold_m=0.12,
    )
    assert short_result["contact_lift_passed"] is True
    assert short_result["retention_passed"] is False


def test_ablation_trace_requires_exact_zero_impulse_no_threshold_and_sub_2cm_rise():
    result = probe.evaluate_zero_friction_trace(
        _ablation_trace(),
        retention_steps=60,
        rise_threshold_m=0.12,
        maximum_rise_m=0.02,
        maximum_friction_anchor_norm_n_s=1.0e-8,
    )
    assert result["protocol_valid"] is True
    assert result["maximum_post_lift_rise_m"] < 0.02
    assert result["threshold_crossed"] is False
    assert result["airborne_retention"] is False
    assert result["causal_negative_passed"] is True

    boundary = _ablation_trace()
    for record in boundary[10:]:
        record["post"]["source_com_m"][2] = 0.02
    failed = probe.evaluate_zero_friction_trace(
        boundary,
        retention_steps=60,
        rise_threshold_m=0.12,
        maximum_rise_m=0.02,
        maximum_friction_anchor_norm_n_s=1.0e-8,
    )
    assert failed["causal_negative_passed"] is False


def test_control_instrumented_comparison_enforces_prefix_continuation_and_margin_rules():
    control = _comparison_summary()
    instrumented = copy.deepcopy(control)
    instrumented["samples"][0]["source_position_m"][0] += 5.0e-5
    result = probe.compare_control_and_instrumented(control, instrumented)
    assert result["comparable"] is True
    assert result["perturbation_detected"] is False

    changed = copy.deepcopy(instrumented)
    changed["continuation"][17]["tool_position_m"][0] = 0.001
    mismatch = probe.compare_control_and_instrumented(control, changed)
    assert mismatch["perturbation_detected"] is True
    assert "continuation_state" in mismatch["failure_reasons"]

    sign_flip = copy.deepcopy(instrumented)
    sign_flip["samples"][0]["predicate_margins"]["inward_cosine"] = -0.1
    margin_mismatch = probe.compare_control_and_instrumented(control, sign_flip)
    assert margin_mismatch["perturbation_detected"] is True
    assert "predicate_margin" in margin_mismatch["failure_reasons"]


def test_physx_combine_priority_and_ablation_isolation_are_exact_and_fail_closed():
    combined = probe.combine_solver_term(
        0.8,
        0.5,
        mode0="average",
        mode1="multiply",
        combine_priority=("average", "min", "multiply", "max"),
    )
    assert combined == {
        "selected_mode": "multiply",
        "value": pytest.approx(0.4),
        "float32_hex": np.float32(0.4).tobytes().hex(),
    }

    original = [
        _pair_row("left-source", target=True, static=0.8, dynamic=0.6),
        _pair_row("left-cube", target=False, static=0.4, dynamic=0.3),
    ]
    ablated = [
        _pair_row("left-source", target=True, static=0.0, dynamic=0.0),
        _pair_row("left-cube", target=False, static=0.4, dynamic=0.3),
    ]
    result = probe.evaluate_ablation_pair_table(original, ablated)
    assert result["protocol_valid"] is True
    assert result["isolated"] is True
    assert result["target_pair_count"] == 1

    changed_non_target = copy.deepcopy(ablated)
    changed_non_target[1]["effective_restitution"] = 0.2
    blocked = probe.evaluate_ablation_pair_table(original, changed_non_target)
    assert blocked["protocol_valid"] is False
    assert "non_target_pair_changed" in blocked["protocol_failures"]

    missing_live = copy.deepcopy(ablated)
    missing_live[0]["runtime_authority"] = "usd_composed_only"
    no_authority = probe.evaluate_ablation_pair_table(original, missing_live)
    assert no_authority["protocol_valid"] is False
    assert "live_material_authority_missing" in no_authority["protocol_failures"]

    negative_zero = copy.deepcopy(ablated)
    negative_zero[0]["effective_static_friction"] = -0.0
    signed_zero = probe.evaluate_ablation_pair_table(original, negative_zero)
    assert signed_zero["protocol_valid"] is False
    assert "target_friction_not_positive_zero" in signed_zero["protocol_failures"]


def test_prohibited_mechanism_audit_requires_complete_bidirectional_zero_write_coverage():
    passed = probe.evaluate_prohibited_mechanism_audit(_complete_audit())
    assert passed["protocol_valid"] is True
    assert passed["zero_write_valid"] is True

    incomplete = _complete_audit()
    incomplete["coverage"]["physics_view_force_at_position"] = False
    blocked = probe.evaluate_prohibited_mechanism_audit(incomplete)
    assert blocked["protocol_valid"] is False
    assert "audit_coverage_incomplete" in blocked["protocol_failures"]

    reverse_filter = _complete_audit()
    reverse_filter["post_reset_counts"]["reverse_filters"] = 1
    filtered = probe.evaluate_prohibited_mechanism_audit(reverse_filter)
    assert filtered["protocol_valid"] is False
    assert "post_reset_prohibited_write" in filtered["protocol_failures"]


def test_parent_finalization_overrides_provisional_pass_on_abnormal_exit_or_cleanup():
    provisional = {
        "schema_version": 1,
        "manifest_type": probe.CHILD_MANIFEST_TYPE,
        "lifecycle_status": "measurement_complete_pending_application_close",
        "treatment": "control",
        "run_nonce": "nonce-1",
        "parent_pid": 111,
        "child_pid": 222,
        "run_id": "run-1",
        "measurement_decision": "ORIGINAL_EMPTY_BEAKER_FRICTION_CAUSAL_PASS",
        "protocol_blockers": [],
    }
    clean = probe.finalize_child_result(
        provisional,
        expected_treatment="control",
        expected_run_nonce="nonce-1",
        expected_parent_pid=111,
        expected_child_pid=222,
        child_command=["python", "probe.py"],
        child_returncode=0,
        timed_out=False,
        termination=None,
        cleanup_quiescent=True,
    )
    assert clean["process_valid"] is True
    assert clean["runtime_error"] is False

    abnormal = probe.finalize_child_result(
        provisional,
        expected_treatment="control",
        expected_run_nonce="nonce-1",
        expected_parent_pid=111,
        expected_child_pid=222,
        child_command=["python", "probe.py"],
        child_returncode=-signal.SIGKILL,
        timed_out=True,
        termination="SIGKILL",
        cleanup_quiescent=True,
    )
    assert abnormal["runtime_error"] is True
    assert abnormal["decision"] == "PROBE_RUNTIME_ERROR"

    escaped = probe.finalize_child_result(
        provisional,
        expected_treatment="control",
        expected_run_nonce="nonce-1",
        expected_parent_pid=111,
        expected_child_pid=222,
        child_command=["python", "probe.py"],
        child_returncode=0,
        timed_out=False,
        termination=None,
        cleanup_quiescent=False,
    )
    assert escaped["runtime_error"] is True
    assert escaped["shutdown_status"] == "cleanup_not_quiescent"


def test_timeout_cleanup_escalates_whole_process_group_and_reaps(monkeypatch):
    class Process:
        pid = 9876
        returncode = None

        def __init__(self):
            self.wait_calls = 0

        def poll(self):
            return None

        def wait(self, timeout):
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise subprocess.TimeoutExpired(["python"], timeout)
            self.returncode = -signal.SIGKILL
            return self.returncode

    process = Process()
    sent = []
    monkeypatch.setattr(
        probe.os,
        "killpg",
        lambda pid, sent_signal: sent.append((pid, sent_signal)),
    )
    termination = probe.terminate_process_group(
        process,
        term_grace_seconds=0.01,
        kill_grace_seconds=0.01,
    )
    assert termination == "SIGKILL"
    assert sent == [
        (9876, signal.SIGTERM),
        (9876, signal.SIGKILL),
    ]
    assert process.wait_calls == 2


def test_quiescence_and_output_confinement_reject_live_or_escaped_descendants(tmp_path):
    class Process:
        pid = 123
        returncode = 0

        def poll(self):
            return self.returncode

    assert probe.validate_process_quiescence(
        Process(),
        process_group_members=lambda _pgid: [],
        collector_closed=True,
    )["quiescent"] is True

    with pytest.raises(RuntimeError, match="probe_process_group_not_quiescent"):
        probe.validate_process_quiescence(
            Process(),
            process_group_members=lambda _pgid: [456],
            collector_closed=True,
        )
    with pytest.raises(RuntimeError, match="probe_collector_not_closed"):
        probe.validate_process_quiescence(
            Process(),
            process_group_members=lambda _pgid: [],
            collector_closed=False,
        )

    root = tmp_path / "treatment"
    root.mkdir()
    assert probe.validate_output_confinement(
        root,
        ["collector/data.hdf5", "hydra/config.yaml", "trace.jsonl"],
    )["valid"] is True
    with pytest.raises(ValueError, match="probe_output_path_escape"):
        probe.validate_output_confinement(root, ["../escaped.hdf5"])


def test_runtime_capability_blocker_maps_to_protocol_no_go_not_weakened_pass():
    report = probe.protocol_no_go_report(
        treatment="zero_friction_ablation",
        run_nonce="nonce-1",
        parent_pid=111,
        child_pid=222,
        run_id="run-1",
        blocker_code="live_solver_cache_authority_unavailable",
        blocker_detail="installed PhysX interface exposes no separable target cache bytes",
    )
    assert report["measurement_decision"] == "PROBE_PROTOCOL_NO_GO"
    assert report["physical_failure"] is False
    assert report["causal_pass"] is False
    assert report["protocol_blockers"] == [
        {
            "code": "live_solver_cache_authority_unavailable",
            "detail": "installed PhysX interface exposes no separable target cache bytes",
        }
    ]


def test_runtime_authority_is_required_before_orientation_calibration():
    class IncompleteSimulationInterface:
        pass

    with pytest.raises(
        probe.ProtocolBlocker,
        match="required_live_physx_authority_unavailable",
    ) as raised:
        probe._require_runtime_authority(IncompleteSimulationInterface())

    assert raised.value.evidence == {
        "required_candidate_methods": {
            "live_solver_pair_materials": [
                "get_effective_contact_pair_material",
                "get_contact_pair_material",
            ],
            "contact_cache_and_warm_start": [
                "get_contact_pair_solver_cache",
                "get_contact_cache",
            ],
            "collision_eligible_pair_matrix": [
                "get_collision_pair_table",
                "get_collision_pairs",
            ],
        },
        "available_methods": {
            "live_solver_pair_materials": [],
            "contact_cache_and_warm_start": [],
            "collision_eligible_pair_matrix": [],
        },
        "missing_authorities": [
            "live_solver_pair_materials",
            "contact_cache_and_warm_start",
            "collision_eligible_pair_matrix",
        ],
        "complete": False,
    }

    source = Path(probe.__file__).read_text(encoding="utf-8")
    assert source.index(
        "authority = _require_runtime_authority(simulation_interface)"
    ) < source.index("orientation = _runtime_orientation_calibration(")
