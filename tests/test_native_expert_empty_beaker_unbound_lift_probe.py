from __future__ import annotations

import ast
import copy
import io
import inspect
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml

from tools.labutopia_fluid import (
    run_native_expert_empty_beaker_unbound_lift_probe as probe,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = (
    REPO_ROOT / "config/diagnostic_level1_pour_native_empty_unbound_lift_v1.yaml"
)
V2_CONFIG_PATH = (
    REPO_ROOT / "config/diagnostic_level1_pour_native_empty_unbound_lift_v2.yaml"
)
V3_CONFIG_PATH = (
    REPO_ROOT / "config/diagnostic_level1_pour_native_empty_unbound_lift_v3.yaml"
)
V4_CONFIG_PATH = (
    REPO_ROOT / "config/diagnostic_level1_pour_native_empty_unbound_lift_v4.yaml"
)
V5_CONFIG_PATH = (
    REPO_ROOT / "config/diagnostic_level1_pour_native_empty_unbound_lift_v5.yaml"
)
V6_CONFIG_PATH = (
    REPO_ROOT / "config/diagnostic_level1_pour_native_empty_unbound_lift_v6.yaml"
)
PRODUCTION_CONFIG_PATH = REPO_ROOT / "config/level1_pour.yaml"
SOURCE = "/World/beaker2/mesh"
SOURCE_ROOT = "/World/beaker2"
SUPPORT = "/World/Cube"
TABLE_SUPPORT = "/World/table/surface/mesh"
LEFT_BODY = "/World/Franka/panda_leftfinger"
RIGHT_BODY = "/World/Franka/panda_rightfinger"
HAND_BODY = "/World/Franka/panda_hand"
LEFT = LEFT_BODY + "/collision"
RIGHT = RIGHT_BODY + "/collision"
HAND = HAND_BODY + "/collision"
LEFT_UNUSED = LEFT_BODY + "/collision_unused"
LOCAL_FRANKA_USD_PATH = "assets/robots/Franka.usd"
LOCAL_FRANKA_SHA256 = "312a326e338949fb40fd245886508cc52cc47e2bebd696e99c7dcdd3d3a7f90b"
LOCAL_SCENE_USD_PATH = (
    "assets/chemistry_lab/lab_001_fluid_eval/dependencies/"
    "lab_001_localized_20260707/lab_001.usd"
)
LOCAL_SCENE_SHA256 = "b3861b5a17945abe401062a04125969c3a63b0f8a0a5ce0026a461dbdfc935f2"
FRANKA_DOF_NAMES = [
    "panda_joint1",
    "panda_joint2",
    "panda_joint3",
    "panda_joint4",
    "panda_joint5",
    "panda_joint6",
    "panda_joint7",
    "panda_finger_joint1",
    "panda_finger_joint2",
]


def _components(**changes):
    result = {
        "runtime_error": False,
        "audit_no_go": False,
        "physical_passed": True,
    }
    result.update(changes)
    return result


def _state(
    z: float,
    *,
    orientation: list[float] | None = None,
    linear: list[float] | None = None,
    angular: list[float] | None = None,
    awake: bool = True,
):
    return {
        "origin_m": [0.0, 0.0, float(z)],
        "orientation_wxyz": orientation or [1.0, 0.0, 0.0, 0.0],
        "linear_velocity_m_s": linear or [0.0, 0.0, 0.0],
        "angular_velocity_rad_s": angular or [0.0, 0.0, 0.0],
        "awake": awake,
    }


def _dynamic_source_contract(**changes):
    result = {
        "source_body_path": SOURCE,
        "source_collider_path": SOURCE,
        "rigid_body_enabled": True,
        "collision_enabled": True,
        "gravity_enabled": True,
        "kinematic_enabled": False,
        "awake": True,
        "scene_owner": "/physicsScene",
        "simulation_owner_targets": ["/physicsScene"],
        "active_scene_contract": {
            "valid": True,
            "physics_context_path": "/physicsScene",
            "physics_scene_paths": ["/physicsScene"],
        },
        "live_physics_membership": {
            "source_body_path": SOURCE,
            "adapter_initialized": True,
            "readbacks": {
                "world_pose": True,
                "linear_velocity": True,
                "angular_velocity": True,
                "physx_is_sleeping": True,
            },
            "state": _state(0.0),
            "valid": True,
        },
        "stage_id": 7,
        "motion_readbacks": {
            "world_pose": True,
            "linear_velocity": True,
            "angular_velocity": True,
            "physx_is_sleeping": True,
        },
        "body_origin_metric": {
            "metric": "rigid_body_origin",
            "authored_center_of_mass_overrides": [],
            "valid": True,
        },
        "source_local_com_authority": {
            "kind": "physx_cooked_rigid_body_properties",
            "source_body_path": SOURCE,
            "stage_id": 7,
            "query_complete": True,
            "query_timing": "pre_task_reset_nonplaying",
            "world_counter_before": 0,
            "world_counter_after": 0,
            "mass_kg": 0.02,
            "center_of_mass_local_m": [0.0, 0.0, 0.0],
            "diagonal_inertia_kg_m2": [0.001, 0.001, 0.001],
            "sealed_sha256": "b" * 64,
        },
        "read_only_adapter": {
            "kind": "omni.isaac.core.prims.RigidPrimView",
            "source_body_path": SOURCE,
            "count": 1,
            "initialized": True,
            "reset_xform_properties": False,
            "prepare_contact_sensors": False,
            "read_only": True,
            "readbacks": {
                "world_pose": True,
                "linear_velocity": True,
                "angular_velocity": True,
            },
        },
    }
    result.update(changes)
    return result


def _cube_snapshot():
    return {
        "world_matrix": [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        "rigid_body_enabled": False,
        "kinematic_enabled": False,
        "velocities": {"linear": [0.0, 0.0, 0.0], "angular": [0.0, 0.0, 0.0]},
        "force_constraint_membership": [],
        "collision_properties": {"enabled": True, "offset": 0.01},
        "material_bindings": {"physics": ["/World/Materials/table"]},
        "group_filter_relationships": {},
        "descendant_physics_state": {
            "colliders": {SUPPORT: {"enabled": True, "contact_offset": 0.01}},
            "material_bindings": {SUPPORT: {"physics": "/World/Materials/table"}},
            "relationships": {},
            "applied_schemas": [],
            "body_state": {
                SUPPORT: {
                    "rigid_body_api": False,
                    "rigid_body_enabled": None,
                    "kinematic_enabled": None,
                }
            },
            "motion_state": {
                SUPPORT: {"linear": [0.0, 0.0, 0.0], "angular": [0.0, 0.0, 0.0]}
            },
        },
        "support_contract": {
            "static": True,
            "nonkinematic": True,
            "nonmoving": True,
            "dynamic_descendant_paths": [],
        },
    }


def _property_snapshot(tag: str = "baseline"):
    return {
        "source": {"mass": 0.02, "gravity": True, "tag": tag},
        "left_finger": {"collision": True, "material": "left", "tag": tag},
        "right_finger": {"collision": True, "material": "right", "tag": tag},
        "hand": {"collision": True, "material": "hand", "tag": tag},
    }


def _writer_audit():
    return {
        "coverage": {name: True for name in probe.REQUIRED_WRITER_AUDIT_SURFACES},
        "surfaces": {
            name: {
                "reachable": True,
                "available": True,
                "audited": True,
                "status": "audited",
            }
            for name in probe.REQUIRED_WRITER_AUDIT_SURFACES
        },
        "static_production_closure": {
            "audit_valid": True,
            "forbidden_calls": [],
            "required_runtime_surfaces": list(probe.REQUIRED_WRITER_AUDIT_SURFACES),
            "not_applicable_runtime_surfaces": [],
        },
        "counts": {name: 0 for name in probe.WRITER_AUDIT_COUNT_FIELDS},
        "reset_root_write_count": 1,
        "zero_write_epoch_opened": True,
        "mutation_notice_active": True,
    }


def _identities(*, support_colliders=None, other_colliders=None):
    support_colliders = list([SUPPORT] if support_colliders is None else support_colliders)
    other_colliders = list([TABLE_SUPPORT] if other_colliders is None else other_colliders)
    other_colliders = [path for path in other_colliders if path not in support_colliders]
    collider_owners = {
        SOURCE: SOURCE,
        LEFT: LEFT_BODY,
        RIGHT: RIGHT_BODY,
        HAND: HAND_BODY,
    }
    collider_owners.update({path: path for path in [*support_colliders, *other_colliders]})
    return {
        "stage_id": 7,
        "source_colliders": [SOURCE],
        "support_colliders": support_colliders,
        "left_colliders": [LEFT],
        "right_colliders": [RIGHT],
        "hand_colliders": [HAND],
        "other_colliders": other_colliders,
        "collider_owners": collider_owners,
    }


def _bound(low, high, *, matrix=None):
    return {
        "local_min_m": list(low),
        "local_max_m": list(high),
        "world_from_local": matrix
        or [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
    }


def _geometry():
    return {
        "gravity_world_m_s2": [0.0, 0.0, -9.81],
        "source": _bound((-1.0, -1.0, 0.0), (1.0, 1.0, 10.0)),
        "source_reset_world_from_local": [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        "finger_colliders": {
            LEFT: _bound((-2.0, -0.5, 1.0), (-1.0, 0.5, 9.0)),
            RIGHT: _bound((1.0, -0.5, 1.0), (2.0, 0.5, 9.0)),
        },
        "pad_edge_margin_m": 0.001,
        "inward_face_distance_tolerance_m": 0.005,
        "normalized_height_range": [0.20, 0.80],
        "maximum_vertical_normal_cosine": 0.25,
        "minimum_inward_face_cosine": 0.8,
    }


def _geometry_with_ambiguous_unused_left_collider():
    geometry = _geometry()
    root_half = math.sqrt(0.5)
    geometry["finger_colliders"][LEFT_UNUSED] = _bound(
        (-2.0, -0.5, 1.0),
        (-1.0, 0.5, 9.0),
        matrix=[
            [root_half, -root_half, 0.0, 0.0],
            [root_half, root_half, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [-1.5 + 1.5 * root_half, -1.5 * root_half, 0.0, 1.0],
        ],
    )
    return geometry


def _identities_with_ambiguous_unused_left_collider():
    identities = _identities()
    identities["left_colliders"].append(LEFT_UNUSED)
    identities["collider_owners"][LEFT_UNUSED] = LEFT_BODY
    return identities


def _local_franka_runtime_identity(*, closure_files=None, prim_stack_layers=None):
    root = (REPO_ROOT / LOCAL_FRANKA_USD_PATH).resolve()
    closure = {
        "entry_path": str(root),
        "entry_sha256": LOCAL_FRANKA_SHA256,
        "files": closure_files
        or [
            {
                "path": str(root),
                "byte_count": root.stat().st_size,
                "sha256": LOCAL_FRANKA_SHA256,
            }
        ],
        "unresolved": [],
    }
    closure["sha256"] = probe._canonical_json_sha256(closure)
    identity = {
        "root_path": "/World/Franka",
        "root_usd_path": LOCAL_FRANKA_USD_PATH,
        "root_absolute_usd_path": str(root),
        "root_sha256": LOCAL_FRANKA_SHA256,
        "dependency_closure": closure,
        "prim_stack_layers": prim_stack_layers
        or [
            {
                "identifier": str(root),
                "real_path": str(root),
                "sha256": LOCAL_FRANKA_SHA256,
            }
        ],
        "dof_names": FRANKA_DOF_NAMES,
        "dof_count": 9,
        "left_finger_body_path": LEFT_BODY,
        "right_finger_body_path": RIGHT_BODY,
        "hand_body_path": HAND_BODY,
    }
    identity["sha256"] = probe._canonical_json_sha256(identity)
    return identity


def _header(
    event: str,
    collider0: str,
    collider1: str,
    *,
    contact_offset: int,
    contact_count: int,
    friction_offset: int = 0,
    friction_count: int = 0,
):
    owners = _identities()["collider_owners"]
    return {
        "type": event,
        "stage_id": 7,
        "actor0": owners[collider0],
        "actor1": owners[collider1],
        "collider0": collider0,
        "collider1": collider1,
        "proto_index0": 0xFFFFFFFF,
        "proto_index1": 0xFFFFFFFF,
        "contact_data_offset": contact_offset,
        "num_contact_data": contact_count,
        "friction_anchors_offset": friction_offset,
        "num_friction_anchors_data": friction_count,
    }


def _point(position, normal):
    return {
        "position": list(position),
        "normal": list(normal),
        "impulse": [0.0, 0.0, 0.0],
        "separation": -0.0001,
        "face_index0": 0,
        "face_index1": 0,
        "material0": "/World/Materials/a",
        "material1": "/World/Materials/b",
    }


def _first_contact_report(*, left_point=None, extra=None):
    left_point = left_point or _point((-1.0, 0.0, 5.0), (1.0, 0.0, 0.0))
    headers = [
        _header("PERSIST", SOURCE, SUPPORT, contact_offset=0, contact_count=1),
        _header("FOUND", SOURCE, LEFT, contact_offset=1, contact_count=1),
        _header("FOUND", SOURCE, RIGHT, contact_offset=2, contact_count=1),
    ]
    contacts = [
        _point((0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        left_point,
        _point((1.0, 0.0, 5.0), (-1.0, 0.0, 0.0)),
    ]
    if extra is not None:
        headers.append(
            _header("FOUND", SOURCE, extra, contact_offset=len(contacts), contact_count=1)
        )
        contacts.append(_point((0.0, 0.0, 5.0), (1.0, 0.0, 0.0)))
    return {"headers": headers, "contact_data": contacts, "friction_anchors": []}


def _empty_contact_report():
    return {"headers": [], "contact_data": [], "friction_anchors": []}


def _support_contact_report(event="FOUND", *, contact_count=1, support=SUPPORT):
    return {
        "headers": [
            _header(
                event,
                SOURCE,
                support,
                contact_offset=0,
                contact_count=contact_count,
            )
        ],
        "contact_data": (
            []
            if contact_count == 0
            else [_point((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))]
        ),
        "friction_anchors": [],
    }


def _composite_support_contact_report(*entries):
    headers = []
    contacts = []
    for event, support, contact_count in entries:
        headers.append(
            _header(
                event,
                SOURCE,
                support,
                contact_offset=len(contacts),
                contact_count=contact_count,
            )
        )
        contacts.extend(
            _point((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
            for _index in range(contact_count)
        )
    return {"headers": headers, "contact_data": contacts, "friction_anchors": []}


def _v3_protocol():
    return probe.resolve_protocol_spec(
        probe.freeze_diagnostic_config(
            V3_CONFIG_PATH,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )["config"]
    )


def _v4_protocol():
    return probe.resolve_protocol_spec(
        probe.freeze_diagnostic_config(
            V4_CONFIG_PATH,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )["config"]
    )


def _v5_protocol():
    return probe.resolve_protocol_spec(
        probe.freeze_diagnostic_config(
            V5_CONFIG_PATH,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )["config"]
    )


def _v6_protocol():
    return probe.resolve_protocol_spec(
        probe.freeze_diagnostic_config(
            V6_CONFIG_PATH,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )["config"]
    )


def _static_support_snapshot(path):
    snapshot = _cube_snapshot()
    snapshot["support_path"] = path
    snapshot["ancestor_body_state"] = {}
    snapshot["descendant_physics_state"] = copy.deepcopy(snapshot["descendant_physics_state"])
    snapshot["descendant_physics_state"]["colliders"] = {
        path: {"enabled": True, "contact_offset": 0.01}
    }
    snapshot["descendant_physics_state"]["material_bindings"] = {
        path: {"physics": "/World/Materials/table"}
    }
    snapshot["descendant_physics_state"]["body_state"] = {
        path: {
            "rigid_body_api": False,
            "rigid_body_enabled": None,
            "kinematic_enabled": None,
        }
    }
    snapshot["descendant_physics_state"]["motion_state"] = {
        path: {"linear": [0.0, 0.0, 0.0], "angular": [0.0, 0.0, 0.0]}
    }
    return snapshot


def _observer_entries(reports, protocol):
    parser = probe.ContactLifecycleAccumulator(_identities(), protocol=protocol)
    observer = probe.SupportObserverAccumulator(protocol=protocol)
    entries = []
    for index, report in enumerate(reports):
        sample = parser.consume(physics_index=index, raw=copy.deepcopy(report))
        decision = observer.consume(
            sample,
            source_state=_state(0.0),
            transition_index=index,
        )
        entries.append(
            {
                "transition_index": index,
                "world_index": index + 1,
                "pre": _state(0.0),
                "post": _state(0.0),
                "raw_report": copy.deepcopy(report),
                "sample": sample,
                "observer": decision,
                "action_context": {
                    "pick_event": None,
                    "action": None,
                    "apply_count": 0,
                    "action_receipt": None,
                    "close_gate": {"audit_no_go_code": None},
                },
            }
        )
    return observer, entries


def _action_record(
    index: int,
    *,
    action=None,
    pick_event=None,
    pour_event=None,
    phase_before="PICKING",
    phase_after="PICKING",
    state_present=True,
    continuation_index=None,
):
    raw_action = None if action is None else probe.raw_action_channels(action)
    canonical = None if raw_action is None else probe.canonicalize_action(raw_action)
    return {
        "transition_index": index,
        "world_index": index + 100,
        "state_present": state_present,
        "controller_call_count": 1 if state_present else 0,
        "phase_before": phase_before,
        "phase_after": phase_after,
        "pick_event": pick_event,
        "pour_event": pour_event,
        "action": raw_action,
        "canonical_action": canonical,
        "apply_count": 0 if raw_action is None else 1,
        "action_receipt": (
            None
            if raw_action is None
            else {
                "applied": True,
                "normal_return": True,
                "apply_count": 1,
                "action_sha256": canonical["sha256"],
            }
        ),
        "integrating_transition_index": None if raw_action is None else index + 1,
        "continuation_index": continuation_index,
        "production_terminal": False,
        "terminal_outcome": None,
        "terminal_success": None,
    }


def _full_relation_inventory(*, relation=None):
    payload = {
        "relations": [] if relation is None else [relation],
        "relationship_topology": [],
        "applied_schemas": [],
        "applied_schema_resolution_complete": True,
    }
    return {**payload, "sha256": probe._canonical_json_sha256(payload)}


def _contact_summary(state: str, *, topology=True, event=None, headers=0):
    return {
        "contact_read_once": True,
        "identity_valid": True,
        "support_state": state,
        "support_event": event,
        "support_header_count": headers,
        "support_contact_count": 0 if event == "LOST" else 1 if state == "CURRENT" else 0,
        "support_friction_anchor_count": 0,
        "source_awake": True,
        "topology": {
            "qualified": topology,
            "failure_reasons": [] if topology else ["missing_bilateral_sidewall"],
        },
        "forbidden_source_contact": False,
        "robot_environment_contact": False,
        "source_support_recontact": False,
    }


def _passing_trace():
    transitions = []
    prior = _state(0.0)
    close_action = {"joint_positions": [None] * 7 + [0.028, 0.028]}
    lift_action = {"joint_positions": [0.0] * 9}
    pour_action = {"joint_velocities": [None] * 6 + [-1.0] + [None, None]}
    for index in range(73):
        continuation = index - 21 if index >= 21 else None
        state_present = continuation is None
        phase_before = "PICKING"
        phase_after = "PICKING"
        action = None
        pick_event = None
        pour_event = None
        if index == 0:
            action, pick_event = close_action, 4
        elif index == 10:
            action, pick_event = lift_action, 5
        elif index == 12:
            phase_after = "POURING"
        elif 13 <= index <= 20:
            phase_before = phase_after = "POURING"
        if index == 14:
            action, pour_event = pour_action, 2
        if continuation is not None:
            phase_before = phase_after = "FINISHED"

        z = 0.0
        support_state = "CURRENT"
        support_event = None
        support_headers = 1
        if index == 12:
            z = 0.05
            support_state = "LOST"
            support_event = "LOST"
            support_headers = 1
        elif index >= 13:
            z = 0.12 if index == 13 else 0.13
            support_state = "LOST"
            support_headers = 0
        orientation = [1.0, 0.0, 0.0, 0.0]
        if index >= 16:
            orientation = [math.cos(math.radians(30.0)), math.sin(math.radians(30.0)), 0.0, 0.0]
        post = _state(z, orientation=orientation)
        record = _action_record(
            index,
            action=action,
            pick_event=pick_event,
            pour_event=pour_event,
            phase_before=phase_before,
            phase_after=phase_after,
            state_present=state_present,
            continuation_index=continuation,
        )
        record["pre"] = copy.deepcopy(prior)
        record["post"] = post
        record["contact"] = _contact_summary(
            support_state,
            event=support_event,
            headers=support_headers,
        )
        if index == 20:
            record["production_terminal"] = True
            record["terminal_outcome"] = "FINISHED"
            record["terminal_success"] = True
        transitions.append(record)
        prior = post
    return transitions


def test_diagnostic_projection_freezes_exact_production_config_and_output_only_differs(
    tmp_path,
):
    frozen = probe.freeze_diagnostic_config(
        CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )
    assert json.loads(frozen["canonical_bytes"]) == frozen["config"]
    assert frozen["canonical_bytes"].endswith(b"\n")
    assert probe.production_visible_projection(frozen["config"]) == (
        probe.production_visible_projection(
            yaml.safe_load(PRODUCTION_CONFIG_PATH.read_text(encoding="utf-8"))
        )
    )
    assert frozen["config"]["max_episodes"] == 1
    assert frozen["config"]["diagnostic"]["numpy_seed"] == 20260718
    assert frozen["config"]["diagnostic"]["child_timeout_seconds"] == 900
    assert frozen["config"]["diagnostic"]["treatments"] == list(probe.TREATMENTS)
    assert frozen["config"]["diagnostic"]["local_franka"] == {
        "usd_path": LOCAL_FRANKA_USD_PATH,
        "sha256": LOCAL_FRANKA_SHA256,
    }
    assert frozen["config"]["diagnostic"]["local_scene"] == {
        "usd_path": LOCAL_SCENE_USD_PATH,
        "sha256": LOCAL_SCENE_SHA256,
    }
    assert frozen["config"]["robot"] == yaml.safe_load(
        PRODUCTION_CONFIG_PATH.read_text(encoding="utf-8")
    )["robot"]
    assert frozen["local_franka"] == {
        "usd_path": LOCAL_FRANKA_USD_PATH,
        "absolute_usd_path": str((REPO_ROOT / LOCAL_FRANKA_USD_PATH).resolve()),
        "sha256": LOCAL_FRANKA_SHA256,
    }
    assert frozen["local_scene"] == {
        "usd_path": LOCAL_SCENE_USD_PATH,
        "absolute_usd_path": str((REPO_ROOT / LOCAL_SCENE_USD_PATH).resolve()),
        "sha256": LOCAL_SCENE_SHA256,
    }
    parent_identity = probe.build_parent_identity(frozen["config"])
    assert parent_identity["local_scene"] == frozen["local_scene"]
    assert parent_identity["asset_dependency_closure"]["entry_path"] == str(
        (REPO_ROOT / LOCAL_SCENE_USD_PATH).resolve()
    )

    control = probe.write_frozen_config(frozen["canonical_bytes"], tmp_path / "control")
    instrumented = probe.write_frozen_config(
        frozen["canonical_bytes"], tmp_path / "instrumented"
    )
    assert control.read_bytes() == instrumented.read_bytes() == frozen["canonical_bytes"]

    drifted = copy.deepcopy(frozen["config"])
    drifted["task"]["max_steps"] = 1499
    drifted_path = tmp_path / "drifted.yaml"
    drifted_path.write_text(yaml.safe_dump(drifted), encoding="utf-8")
    with pytest.raises(ValueError, match="native_unbound_production_projection_mismatch"):
        probe.freeze_diagnostic_config(
            drifted_path,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )

    escaped = copy.deepcopy(frozen["config"])
    escaped["multi_run"]["run_dir"] = "../escape"
    escaped_path = tmp_path / "escaped.yaml"
    escaped_path.write_text(yaml.safe_dump(escaped), encoding="utf-8")
    with pytest.raises(ValueError, match="native_unbound_output_route_invalid"):
        probe.freeze_diagnostic_config(
            escaped_path,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )


def test_protocol_registry_keeps_v1_frozen_and_admits_only_the_pinned_v2_contract(tmp_path):
    v1 = probe.freeze_diagnostic_config(
        CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )
    v2 = probe.freeze_diagnostic_config(
        V2_CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )
    v1_protocol = probe.resolve_protocol_spec(v1["config"])
    v2_protocol = probe.resolve_protocol_spec(v2["config"])

    assert v1_protocol["schema_version"] == 1
    assert v1_protocol["protocol_id"] == "native_expert_empty_beaker_unbound_lift_v1"
    assert v1_protocol["initial_support_activation_max_absent_reports"] == 0
    assert v2_protocol["schema_version"] == 2
    assert v2_protocol["protocol_id"] == "native_expert_empty_beaker_unbound_lift_v2"
    assert v2_protocol["initial_support_activation_max_absent_reports"] == 10
    assert v2["config"]["diagnostic"]["initial_support_activation_max_absent_reports"] == 10
    assert probe.production_visible_projection(v1["config"]) == probe.production_visible_projection(
        v2["config"]
    )

    altered_v1 = copy.deepcopy(v1["config"])
    altered_v1["diagnostic"]["initial_support_activation_max_absent_reports"] = 10
    altered_v1_path = tmp_path / "v1-with-v2-policy.yaml"
    altered_v1_path.write_text(yaml.safe_dump(altered_v1), encoding="utf-8")
    with pytest.raises(ValueError, match="native_unbound_pinned_contract_mismatch"):
        probe.freeze_diagnostic_config(
            altered_v1_path,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )


def test_v3_pins_the_exact_cube_and_table_support_set_without_changing_v1_or_v2(tmp_path):
    v1 = probe.freeze_diagnostic_config(
        CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )
    v2 = probe.freeze_diagnostic_config(
        V2_CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )
    v3 = probe.freeze_diagnostic_config(
        V3_CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )
    v3_protocol = probe.resolve_protocol_spec(v3["config"])

    assert v3_protocol["schema_version"] == 3
    assert v3_protocol["protocol_id"] == "native_expert_empty_beaker_unbound_lift_v3"
    assert v3_protocol["support_collider_paths"] == [SUPPORT, TABLE_SUPPORT]
    assert v3["config"]["diagnostic"]["support_collider_paths"] == [SUPPORT, TABLE_SUPPORT]
    assert "support_collider_path" not in v3["config"]["diagnostic"]
    assert probe.production_visible_projection(v1["config"]) == probe.production_visible_projection(
        v2["config"]
    ) == probe.production_visible_projection(v3["config"])

    reordered = copy.deepcopy(v3["config"])
    reordered["diagnostic"]["support_collider_paths"] = [TABLE_SUPPORT, SUPPORT]
    reordered_path = tmp_path / "v3-reordered-supports.yaml"
    reordered_path.write_text(yaml.safe_dump(reordered), encoding="utf-8")
    with pytest.raises(ValueError, match="native_unbound_pinned_contract_mismatch"):
        probe.freeze_diagnostic_config(
            reordered_path,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )


def test_v4_pins_observation_gap_continuation_without_rewriting_v3():
    v3 = probe.freeze_diagnostic_config(
        V3_CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )
    v4 = probe.freeze_diagnostic_config(
        V4_CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )
    protocol = probe.resolve_protocol_spec(v4["config"])

    assert protocol["schema_version"] == 4
    assert protocol["protocol_id"] == "native_expert_empty_beaker_unbound_lift_v4"
    assert protocol["allow_active_support_pair_omission"] is True
    assert protocol["support_collider_paths"] == [SUPPORT, TABLE_SUPPORT]
    assert v4["config"]["diagnostic"]["allow_active_support_pair_omission"] is True
    assert "allow_active_support_pair_omission" not in v3["config"]["diagnostic"]
    assert probe.production_visible_projection(v3["config"]) == probe.production_visible_projection(
        v4["config"]
    )


def test_v5_pins_closed_grasp_topology_scope_without_rewriting_v4():
    v4 = probe.freeze_diagnostic_config(
        V4_CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )
    v5 = probe.freeze_diagnostic_config(
        V5_CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )
    protocol = probe.resolve_protocol_spec(v5["config"])

    assert protocol["schema_version"] == 5
    assert protocol["protocol_id"] == "native_expert_empty_beaker_unbound_lift_v5"
    assert protocol["allow_active_support_pair_omission"] is True
    assert protocol["topology_required_from_close_to_rise"] is True
    assert v5["config"]["diagnostic"]["topology_required_from_close_to_rise"] is True
    assert "topology_required_from_close_to_rise" not in v4["config"]["diagnostic"]
    assert probe.production_visible_projection(v4["config"]) == probe.production_visible_projection(
        v5["config"]
    )


def test_v6_pins_loaded_contact_and_world_metric_evidence_without_rewriting_v5():
    v5 = probe.freeze_diagnostic_config(
        V5_CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )
    v6 = probe.freeze_diagnostic_config(
        V6_CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )
    protocol = probe.resolve_protocol_spec(v6["config"])

    assert protocol["schema_version"] == 6
    assert protocol["protocol_id"] == "native_expert_empty_beaker_unbound_lift_v6"
    assert protocol["topology_world_metric_distances"] is True
    assert protocol["contact_load_bearing_authority"] is True
    assert protocol["minimum_noncontact_clearance_m"] == pytest.approx(0.005)
    assert v6["config"]["diagnostic"]["topology_world_metric_distances"] is True
    assert v6["config"]["diagnostic"]["topology"][
        "inward_face_distance_tolerance_m"
    ] == pytest.approx(0.005)
    assert "topology_world_metric_distances" not in v5["config"]["diagnostic"]
    assert probe.production_visible_projection(v5["config"]) == probe.production_visible_projection(
        v6["config"]
    )


def test_v4_continues_only_an_omitted_active_support_pair_with_observed_only_evidence():
    identities = _identities(
        support_colliders=[SUPPORT, TABLE_SUPPORT],
        other_colliders=[],
    )
    found_both = _composite_support_contact_report(
        ("FOUND", SUPPORT, 1),
        ("FOUND", TABLE_SUPPORT, 1),
    )

    v3 = probe.ContactLifecycleAccumulator(identities, protocol=_v3_protocol())
    v3.consume(physics_index=0, raw=copy.deepcopy(found_both))
    with pytest.raises(probe.ContactAuditError, match="contact_active_pair_missing"):
        v3.consume(physics_index=1, raw=_empty_contact_report())

    v4 = probe.ContactLifecycleAccumulator(identities, protocol=_v4_protocol())
    v4.consume(physics_index=0, raw=copy.deepcopy(found_both))
    gap = v4.consume(physics_index=1, raw=_empty_contact_report())
    expected_pairs = [sorted((SOURCE, SUPPORT)), sorted((SOURCE, TABLE_SUPPORT))]
    assert gap["pairs"] == []
    assert gap["support_observation_gap"] is True
    assert gap["unreported_active_pairs"] == expected_pairs
    assert gap["support"]["support_observation_gap"] is True
    assert gap["support"]["unreported_active_pairs"] == expected_pairs
    assert gap["support"]["contact_count"] == 0
    assert v4.active == {tuple(pair) for pair in expected_pairs}

    recovered = v4.consume(
        physics_index=2,
        raw=_composite_support_contact_report(
            ("PERSIST", SUPPORT, 1),
            ("PERSIST", TABLE_SUPPORT, 1),
        ),
    )
    assert recovered["unreported_active_pairs"] == []
    assert recovered["support_observation_gap"] is False
    lost = v4.consume(
        physics_index=3,
        raw=_composite_support_contact_report(
            ("LOST", SUPPORT, 0),
            ("LOST", TABLE_SUPPORT, 0),
        ),
    )
    assert lost["support"]["lost_header_count"] == 2


def test_v4_observer_requires_the_parser_observation_gap_boolean():
    protocol = _v4_protocol()
    identities = _identities(
        support_colliders=[SUPPORT, TABLE_SUPPORT],
        other_colliders=[],
    )
    parser = probe.ContactLifecycleAccumulator(identities, protocol=protocol)
    found = parser.consume(
        physics_index=0,
        raw=_composite_support_contact_report(
            ("FOUND", SUPPORT, 1),
            ("FOUND", TABLE_SUPPORT, 1),
        ),
    )
    gap = parser.consume(physics_index=1, raw=_empty_contact_report())
    observer = probe.SupportObserverAccumulator(protocol=protocol)
    observer.consume(found, source_state=_state(0.0), transition_index=0)
    tampered = copy.deepcopy(gap)
    tampered["support_observation_gap"] = False

    decision = observer.consume(tampered, source_state=_state(0.0), transition_index=1)

    assert decision["audit_no_go_code"] == "support_observation_gap_authority_missing"


def test_v4_preserves_active_support_state_across_partial_and_consecutive_gaps():
    protocol = _v4_protocol()
    identities = _identities(
        support_colliders=[SUPPORT, TABLE_SUPPORT],
        other_colliders=[],
    )
    parser = probe.ContactLifecycleAccumulator(identities, protocol=protocol)
    observer = probe.SupportObserverAccumulator(protocol=protocol)
    found = parser.consume(
        physics_index=0,
        raw=_composite_support_contact_report(
            ("FOUND", SUPPORT, 1),
            ("FOUND", TABLE_SUPPORT, 1),
        ),
    )
    observer.consume(found, source_state=_state(0.0), transition_index=0)
    expected_missing = [sorted((SOURCE, TABLE_SUPPORT))]

    for index in (1, 2):
        partial = parser.consume(
            physics_index=index,
            raw=_support_contact_report("PERSIST", support=SUPPORT),
        )
        decision = observer.consume(
            partial,
            source_state=_state(0.0),
            transition_index=index,
        )
        assert partial["support_observation_gap"] is True
        assert partial["unreported_active_pairs"] == expected_missing
        assert decision["state"] == "CURRENT"
        assert decision["support_observation_gap"] is True
        assert parser.active == {
            tuple(sorted((SOURCE, SUPPORT))),
            tuple(sorted((SOURCE, TABLE_SUPPORT))),
        }

    recovered = parser.consume(
        physics_index=3,
        raw=_composite_support_contact_report(
            ("PERSIST", SUPPORT, 1),
            ("PERSIST", TABLE_SUPPORT, 1),
        ),
    )
    recovered_decision = observer.consume(
        recovered,
        source_state=_state(0.0),
        transition_index=3,
    )
    assert recovered_decision["support_observation_gap"] is False


def test_v4_rejects_an_omitted_active_non_support_pair_atomically():
    identities = _identities(
        support_colliders=[SUPPORT, TABLE_SUPPORT],
        other_colliders=[],
    )
    report = _support_contact_report("FOUND", support=SUPPORT)
    report["headers"].append(
        _header("FOUND", SOURCE, LEFT, contact_offset=1, contact_count=1)
    )
    report["contact_data"].append(_point((-1.0, 0.0, 5.0), (1.0, 0.0, 0.0)))
    parser = probe.ContactLifecycleAccumulator(identities, protocol=_v4_protocol())
    parser.consume(physics_index=0, raw=report)

    with pytest.raises(probe.ContactAuditError, match="contact_active_pair_missing"):
        parser.consume(physics_index=1, raw=_empty_contact_report())
    assert parser.active == {tuple(sorted((SOURCE, SUPPORT))), tuple(sorted((SOURCE, LEFT)))}


def test_contact_parser_rejects_a_noninteger_stage_identifier():
    report = _support_contact_report("FOUND")
    report["headers"][0]["stage_id"] = 7.0

    with pytest.raises(probe.ContactAuditError, match="contact_header_semantics_invalid"):
        probe.ContactLifecycleAccumulator(_identities()).consume(
            physics_index=0,
            raw=report,
        )


def test_runtime_contact_reporter_converts_malformed_vectors_to_audit_no_go():
    class Interface:
        def get_full_contact_report(self):
            return None, [], []

    reporter = probe._RuntimeFullContactReporter(
        simulation_interface=Interface(),
        resolve_path=lambda identifier: f"/World/{identifier}",
    )

    with pytest.raises(probe.AuditNoGo, match="contact_record_semantics_unsupported"):
        reporter.sample(physics_index=0)


def test_v4_observer_keeps_native_close_unmodified_across_a_recoverable_gap():
    protocol = _v4_protocol()
    identities = _identities(
        support_colliders=[SUPPORT, TABLE_SUPPORT],
        other_colliders=[],
    )
    parser = probe.ContactLifecycleAccumulator(identities, protocol=protocol)
    observer = probe.SupportObserverAccumulator(protocol=protocol)
    found = parser.consume(
        physics_index=0,
        raw=_composite_support_contact_report(
            ("FOUND", SUPPORT, 1),
            ("FOUND", TABLE_SUPPORT, 1),
        ),
    )
    assert observer.consume(
        found,
        source_state=_state(0.0),
        transition_index=0,
    )["state"] == "CURRENT"

    gap = parser.consume(physics_index=1, raw=_empty_contact_report())
    gap_decision = observer.consume(
        gap,
        source_state=_state(0.0),
        transition_index=1,
    )
    assert gap_decision["state"] == "CURRENT"
    assert gap_decision["support_observation_gap"] is True
    assert gap_decision["unreported_active_pairs"] == [
        sorted((SOURCE, SUPPORT)),
        sorted((SOURCE, TABLE_SUPPORT)),
    ]
    assert observer.observe_action(
        pick_event=4,
        action={"joint_positions": [0.0] * 9},
        apply_count=1,
        action_receipt={"applied": True, "normal_return": True, "apply_count": 1},
        classifications=[],
    ) == {"audit_no_go_code": None}

    recovered = parser.consume(
        physics_index=2,
        raw=_composite_support_contact_report(
            ("PERSIST", SUPPORT, 1),
            ("PERSIST", TABLE_SUPPORT, 1),
        ),
    )
    recovered_decision = observer.consume(
        recovered,
        source_state=_state(0.0),
        transition_index=2,
    )
    assert recovered_decision["support_observation_gap"] is False
    assert recovered_decision["unreported_active_pairs"] == []


def _v4_parent_replay_fixture():
    protocol = _v4_protocol()
    identities = _identities(
        support_colliders=[SUPPORT, TABLE_SUPPORT],
        other_colliders=[],
    )
    reports = [
        _composite_support_contact_report(
            ("FOUND", SUPPORT, 1),
            ("FOUND", TABLE_SUPPORT, 1),
        ),
        _empty_contact_report(),
        _composite_support_contact_report(
            ("PERSIST", SUPPORT, 1),
            ("PERSIST", TABLE_SUPPORT, 1),
        ),
        _composite_support_contact_report(
            ("LOST", SUPPORT, 0),
            ("LOST", TABLE_SUPPORT, 0),
        ),
    ]
    for index, report in enumerate(reports):
        report.update(
            {
                "physics_index": index,
                "immediate_read_index": index,
                "immediate_read_count": index + 1,
            }
        )
    contacts = probe.evaluate_contact_trace(
        reports,
        identities=identities,
        geometry=[_geometry() for _index in reports],
        require_immediate_read=True,
        protocol=protocol,
    )
    lifecycle = probe.evaluate_support_lifecycle(
        contacts["samples"],
        [_state(0.0) for _index in reports],
        protocol=protocol,
        action_contexts=[
            {"pick_event": None, "action": None, "apply_count": 0, "action_receipt": None}
            for _index in reports
        ],
    )
    assert contacts["audit_valid"] is True
    assert lifecycle["audit_valid"] is True
    transitions = []
    for index, (report, sample, decision) in enumerate(
        zip(reports, contacts["samples"], lifecycle["decisions"])
    ):
        summary = probe._runtime_contact_summary(
            sample,
            source_awake=True,
            observer_decision=decision,
        )
        summary["source_support_recontact"] = False
        transitions.append(
            {
                "transition_index": index,
                "post": _state(0.0),
                "pick_event": None,
                "action": None,
                "apply_count": 0,
                "action_receipt": None,
                "contact": {
                    "raw_report": copy.deepcopy(report),
                    "geometry": _geometry(),
                    **summary,
                },
            }
        )
    return transitions, {"contact_identities": identities, "protocol": protocol}, protocol


def _v4_gap_journal(transitions, evidence, protocol, *, index=1):
    parser = probe.ContactLifecycleAccumulator(
        evidence["contact_identities"],
        protocol=protocol,
    )
    sample = None
    for transition_index in range(index + 1):
        sample = parser.consume(
            physics_index=transition_index,
            raw=copy.deepcopy(transitions[transition_index]["contact"]["raw_report"]),
        )
    assert sample is not None
    return {
        "transition_index": index,
        "raw_report": copy.deepcopy(transitions[index]["contact"]["raw_report"]),
        "parser_sample": probe._v4_observation_gap_sample_projection(
            sample,
            protocol=protocol,
        ),
    }


def test_v4_parent_replays_observation_gap_journal_prefix_and_rejects_tampering():
    transitions, evidence, protocol = _v4_parent_replay_fixture()
    journal = [_v4_gap_journal(transitions, evidence, protocol)]

    accepted = probe._parent_recompute_v4_observation_gap_prefix(
        transitions[:1],
        journal,
        evidence,
        protocol=protocol,
    )
    assert accepted["audit_valid"] is True
    assert accepted["contact_replay"]["audit_valid"] is True

    completed = probe._parent_recompute_v4_observation_gap_prefix(
        transitions,
        journal,
        evidence,
        protocol=protocol,
    )
    assert completed["audit_valid"] is True

    tampered = copy.deepcopy(journal)
    tampered[0]["parser_sample"]["support_observation_gap"] = False
    rejected = probe._parent_recompute_v4_observation_gap_prefix(
        transitions[:1],
        tampered,
        evidence,
        protocol=protocol,
    )
    assert rejected["audit_valid"] is False
    assert "instrumented_v4_observation_gap_journal_invalid" in rejected["audit_failures"]

    altered_support = copy.deepcopy(journal)
    altered_support[0]["parser_sample"]["support"]["current"] = True
    rejected_support = probe._parent_recompute_v4_observation_gap_prefix(
        transitions[:1],
        altered_support,
        evidence,
        protocol=protocol,
    )
    assert rejected_support["audit_valid"] is False
    assert "instrumented_v4_observation_gap_journal_invalid" in rejected_support[
        "audit_failures"
    ]

    injected = copy.deepcopy(journal)
    injected[0]["action"] = {"joint_positions": [0.0] * 9}
    rejected_injected = probe._parent_recompute_v4_observation_gap_prefix(
        transitions[:1],
        injected,
        evidence,
        protocol=protocol,
    )
    assert rejected_injected["audit_valid"] is False
    assert "instrumented_v4_observation_gap_journal_invalid" in rejected_injected[
        "audit_failures"
    ]

    missing = probe._parent_recompute_v4_observation_gap_prefix(
        transitions,
        [],
        evidence,
        protocol=protocol,
    )
    assert missing["audit_valid"] is False
    assert "instrumented_v4_observation_gap_journal_missing" in missing["audit_failures"]


def test_trace_accepts_an_observation_gap_journal_before_audit_no_go():
    records = []
    trace_identity = {
        "treatment": "instrumented",
        "run_nonce": "nonce",
        "parent_pid": 1,
        "child_pid": 2,
        "run_id": "run",
    }
    for kind, payload in (
        ("bootstrap", {"runtime_evidence": {}}),
        ("observation_gap", {"transition_index": 1}),
        ("audit_no_go", {"code": "boundary_failure", "detail": "test", "evidence": None}),
        (
            "terminal",
            {
                "runtime_status": "audit_no_go",
                "lifecycle_status": probe.CHILD_LIFECYCLE_BY_RUNTIME_STATUS["audit_no_go"],
            },
        ),
    ):
        records.append(probe.make_trace_record(records, kind=kind, payload=payload, **trace_identity))

    validated = probe.validate_trace_records(records, **{
        "expected_treatment": "instrumented",
        "expected_nonce": "nonce",
        "expected_parent_pid": 1,
        "expected_child_pid": 2,
        "expected_run_id": "run",
    })

    assert validated["runtime_status"] == "audit_no_go"


def test_v4_runtime_journals_an_accepted_gap_before_a_later_boundary_failure(monkeypatch):
    protocol = _v4_protocol()
    identities = _identities(
        support_colliders=[SUPPORT, TABLE_SUPPORT],
        other_colliders=[],
    )
    accumulator = probe.ContactLifecycleAccumulator(identities, protocol=protocol)
    observer = probe.SupportObserverAccumulator(protocol=protocol)
    found = accumulator.consume(
        physics_index=0,
        raw=_composite_support_contact_report(
            ("FOUND", SUPPORT, 1),
            ("FOUND", TABLE_SUPPORT, 1),
        ),
    )
    observer.consume(found, source_state=_state(0.0), transition_index=0)

    class World:
        current_time_step_index = 0

        def step(self, *, render):
            assert render is True
            self.current_time_step_index += 1

    class Reporter:
        def sample(self, *, physics_index):
            assert physics_index == 1
            return _empty_contact_report()

    class Notice:
        def mark(self):
            return 0

        def capture_since(self, _marker, *, phase):
            assert phase == "world_step"
            return {"events": []}

    monkeypatch.setattr(probe, "_runtime_source_state", lambda *_args, **_kwargs: _state(0.0))
    monkeypatch.setattr(probe, "_runtime_live_geometry", lambda *_args, **_kwargs: _geometry())
    monkeypatch.setattr(
        probe,
        "evaluate_sidewall_topology",
        lambda *_args, **_kwargs: {"audit_valid": True, "audit_failures": []},
    )

    def fail_boundary(*_args, **_kwargs):
        raise probe.AuditNoGo("forced_boundary_failure", "after observation")

    monkeypatch.setattr(probe, "_runtime_transition_boundary", fail_boundary)
    journal = []

    with pytest.raises(probe.AuditNoGo, match="forced_boundary_failure"):
        probe._runtime_production_transition(
            transition_index=1,
            world=World(),
            task=None,
            controller=None,
            robot=None,
            source_body=object(),
            simulation_interface=object(),
            stage_id=1,
            sdf_path_to_int=lambda _path: 1,
            reporter=Reporter(),
            contact_accumulator=accumulator,
            support_observer=observer,
            support_state="CURRENT",
            initial_support_observations=[],
            protocol=protocol,
            stage=object(),
            sealed_geometry=_geometry(),
            identities=identities,
            mutation_notice=Notice(),
            mutation_marker=0,
            relation_baseline_sha256="0" * 64,
            apply_index=0,
            video=None,
            video_sample_every_transitions=1,
            observation_gap_sink=journal.append,
        )

    assert len(journal) == 1
    assert journal[0]["transition_index"] == 1
    assert journal[0]["raw_report"] == _empty_contact_report()
    assert journal[0]["parser_sample"]["support_observation_gap"] is True


def test_v4_runtime_journals_an_accepted_gap_before_topology_failure(monkeypatch):
    protocol = _v4_protocol()
    identities = _identities(
        support_colliders=[SUPPORT, TABLE_SUPPORT],
        other_colliders=[],
    )
    accumulator = probe.ContactLifecycleAccumulator(identities, protocol=protocol)
    observer = probe.SupportObserverAccumulator(protocol=protocol)
    found = accumulator.consume(
        physics_index=0,
        raw=_composite_support_contact_report(
            ("FOUND", SUPPORT, 1),
            ("FOUND", TABLE_SUPPORT, 1),
        ),
    )
    observer.consume(found, source_state=_state(0.0), transition_index=0)

    class World:
        current_time_step_index = 0

        def step(self, *, render):
            assert render is True
            self.current_time_step_index += 1

    class Reporter:
        def sample(self, *, physics_index):
            assert physics_index == 1
            return _empty_contact_report()

    class Notice:
        def mark(self):
            return 0

        def capture_since(self, _marker, *, phase):
            assert phase == "world_step"
            return {"events": []}

    monkeypatch.setattr(probe, "_runtime_source_state", lambda *_args, **_kwargs: _state(0.0))
    monkeypatch.setattr(probe, "_runtime_live_geometry", lambda *_args, **_kwargs: _geometry())
    monkeypatch.setattr(
        probe,
        "evaluate_sidewall_topology",
        lambda *_args, **_kwargs: {
            "audit_valid": False,
            "audit_failures": ["forced_topology_failure"],
        },
    )
    journal = []

    with pytest.raises(probe.AuditNoGo, match="contact_topology_authority_invalid") as error:
        probe._runtime_production_transition(
            transition_index=1,
            world=World(),
            task=None,
            controller=None,
            robot=None,
            source_body=object(),
            simulation_interface=object(),
            stage_id=1,
            sdf_path_to_int=lambda _path: 1,
            reporter=Reporter(),
            contact_accumulator=accumulator,
            support_observer=observer,
            support_state="CURRENT",
            initial_support_observations=[],
            protocol=protocol,
            stage=object(),
            sealed_geometry=_geometry(),
            identities=identities,
            mutation_notice=Notice(),
            mutation_marker=0,
            relation_baseline_sha256="0" * 64,
            apply_index=0,
            video=None,
            video_sample_every_transitions=1,
            observation_gap_sink=journal.append,
        )

    assert len(journal) == 1
    assert journal[0]["parser_sample"]["support_observation_gap"] is True
    assert error.value.evidence["raw_report"] == _empty_contact_report()
    assert error.value.evidence["observation_gap_journal"] == journal[0]


def _v4_trace_with_gap(gap_index=None):
    trace = _passing_trace()
    for index, transition in enumerate(trace):
        lost = index >= 12
        transition["contact"].update(
            {
                "initial_support_absent_reports": 0,
                "initial_support_prefix_physical_failures": [],
                "support_pair_physical_failures": [],
                "support_observation_gap": index == gap_index,
                "unreported_active_pairs": (
                    [sorted((SOURCE, SUPPORT)), sorted((SOURCE, TABLE_SUPPORT))]
                    if index == gap_index
                    else []
                ),
                "support_pairs": [
                    {
                        "pair": sorted((SOURCE, SUPPORT)),
                        "ever_current": True,
                        "current": not lost,
                        "terminal_lost": lost,
                    },
                    {
                        "pair": sorted((SOURCE, TABLE_SUPPORT)),
                        "ever_current": True,
                        "current": not lost,
                        "terminal_lost": lost,
                    },
                ],
            }
        )
    return trace


def _v6_trace():
    trace = _v4_trace_with_gap()
    for transition in trace:
        transition["contact"].update(
            {
                "physical_classifications": [],
                "noncontact_clearance_m": {},
            }
        )
    return trace


def test_v4_allows_an_early_recovered_gap_but_rejects_gaps_in_every_decisive_interval():
    protocol = _v4_protocol()
    accepted = probe.evaluate_native_lift_pour_trace(
        _v4_trace_with_gap(0),
        retention_steps=60,
        rise_threshold_m=0.12,
        initial_support_activation_max_absent_reports=10,
        protocol=protocol,
    )
    assert accepted["audit_valid"] is True
    assert accepted["physical_passed"] is True

    for index in (1, 10, 11, 12, 13, 14, 15, 16, 72):
        rejected = probe.evaluate_native_lift_pour_trace(
            _v4_trace_with_gap(index),
            retention_steps=60,
            rise_threshold_m=0.12,
            initial_support_activation_max_absent_reports=10,
            protocol=protocol,
        )
        assert rejected["audit_valid"] is True
        assert rejected["physical_passed"] is False

    missing = _v4_trace_with_gap()
    missing[0]["contact"].pop("support_observation_gap")
    missing[0]["contact"].pop("unreported_active_pairs")
    rejected_missing = probe.evaluate_native_lift_pour_trace(
        missing,
        retention_steps=60,
        rise_threshold_m=0.12,
        initial_support_activation_max_absent_reports=10,
        protocol=protocol,
    )
    assert rejected_missing["audit_valid"] is False


def test_v5_requires_qualified_topology_from_close_integration_through_rise():
    protocol = _v5_protocol()
    preclose_only = _v4_trace_with_gap()
    preclose_only[0]["contact"]["topology"]["qualified"] = False
    accepted = probe.evaluate_native_lift_pour_trace(
        preclose_only,
        retention_steps=60,
        rise_threshold_m=0.12,
        initial_support_activation_max_absent_reports=10,
        protocol=protocol,
    )
    assert accepted["audit_valid"] is True
    assert accepted["physical_passed"] is True

    after_close = _v4_trace_with_gap()
    after_close[1]["contact"]["topology"]["qualified"] = False
    rejected = probe.evaluate_native_lift_pour_trace(
        after_close,
        retention_steps=60,
        rise_threshold_m=0.12,
        initial_support_activation_max_absent_reports=10,
        protocol=protocol,
    )
    assert rejected["audit_valid"] is True
    assert rejected["physical_passed"] is False
    assert "bilateral_middle_sidewall_topology_missing" in rejected["physical_failures"]


def test_v6_rejects_preclose_loaded_finger_contact_and_insufficient_proximity_clearance():
    protocol = _v6_protocol()
    preclose = _v6_trace()
    preclose[0]["contact"]["physical_classifications"] = ["RIGHT_SOURCE"]
    rejected = probe.evaluate_native_lift_pour_trace(
        preclose,
        retention_steps=60,
        rise_threshold_m=0.12,
        initial_support_activation_max_absent_reports=10,
        protocol=protocol,
    )
    assert rejected["audit_valid"] is True
    assert rejected["physical_passed"] is False
    assert "preclose_force_bearing_source_finger_contact" in rejected["physical_failures"]

    clearance = _v6_trace()
    clearance[2]["contact"]["noncontact_clearance_m"] = {"SOURCE_OTHER": 0.004}
    rejected = probe.evaluate_native_lift_pour_trace(
        clearance,
        retention_steps=60,
        rise_threshold_m=0.12,
        initial_support_activation_max_absent_reports=10,
        protocol=protocol,
    )
    assert rejected["audit_valid"] is True
    assert rejected["physical_passed"] is False
    assert "forbidden_source_proximity_clearance" in rejected["physical_failures"]


def test_v6_counts_loaded_transient_contacts_but_not_pure_lost_pairs():
    transient_report = {
        "headers": [
            _header("FOUND", SOURCE, HAND, contact_offset=0, contact_count=1),
            _header("LOST", SOURCE, HAND, contact_offset=1, contact_count=0),
        ],
        "contact_data": [_point((0.0, 0.0, 5.0), (1.0, 0.0, 0.0))],
        "friction_anchors": [],
    }
    sample = probe.ContactLifecycleAccumulator(
        _identities(support_colliders=[SUPPORT, TABLE_SUPPORT], other_colliders=[]),
        protocol=_v6_protocol(),
    ).consume(physics_index=0, raw=transient_report)

    assert sample["pairs"][0]["current"] is False
    assert sample["pairs"][0]["transient"] is True
    assert probe._contact_physical_evidence(
        sample, protocol=_v6_protocol()
    )["physical_classifications"] == ["SOURCE_OTHER"]

    lost_only = {
        "headers": [_header("LOST", SOURCE, HAND, contact_offset=0, contact_count=0)],
        "contact_data": [],
        "friction_anchors": [],
    }
    sample = probe.ContactLifecycleAccumulator(
        _identities(support_colliders=[SUPPORT, TABLE_SUPPORT], other_colliders=[]),
        protocol=_v6_protocol(),
    ).consume(physics_index=0, raw=lost_only)
    assert probe._contact_physical_evidence(
        sample, protocol=_v6_protocol()
    )["physical_classifications"] == []


def test_close_observer_gate_does_not_reparse_an_unavailable_sample():
    observer = probe.SupportObserverAccumulator(protocol=_v6_protocol())
    observer.state = "CURRENT"

    gate = observer.observe_action(
        pick_event=4,
        action={"joint_positions": [0.0] * 9},
        apply_count=1,
        action_receipt={"applied": True, "normal_return": True, "apply_count": 1},
        classifications=[],
    )

    assert gate == {"audit_no_go_code": None}


def test_v3_classifies_only_the_exact_table_surface_as_allowed_source_support():
    v2_protocol = probe.resolve_protocol_spec(
        probe.freeze_diagnostic_config(
            V2_CONFIG_PATH,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )["config"]
    )
    report = _support_contact_report("FOUND", support=TABLE_SUPPORT)
    v2 = probe.evaluate_contact_trace(
        [report],
        identities=_identities(),
        geometry=_geometry(),
        protocol=v2_protocol,
    )
    assert v2["audit_valid"] is True
    assert v2["samples"][0]["classifications"] == ["SOURCE_OTHER"]

    v3 = probe.evaluate_contact_trace(
        [report],
        identities=_identities(
            support_colliders=[SUPPORT, TABLE_SUPPORT],
            other_colliders=[],
        ),
        geometry=_geometry(),
        protocol=_v3_protocol(),
    )
    assert v3["audit_valid"] is True
    assert v3["samples"][0]["classifications"] == ["SOURCE_SUPPORT"]


def test_v3_requires_explicit_loss_of_every_seen_support_pair_before_aggregate_loss():
    protocol = _v3_protocol()
    identities = _identities(
        support_colliders=[SUPPORT, TABLE_SUPPORT],
        other_colliders=[],
    )
    reports = [
        _composite_support_contact_report(
            ("FOUND", SUPPORT, 1),
            ("FOUND", TABLE_SUPPORT, 1),
        ),
        _composite_support_contact_report(
            ("LOST", SUPPORT, 0),
            ("PERSIST", TABLE_SUPPORT, 1),
        ),
        _composite_support_contact_report(("LOST", TABLE_SUPPORT, 0)),
    ]
    parsed = probe.evaluate_contact_trace(
        reports,
        identities=identities,
        geometry=[_geometry() for _report in reports],
        protocol=protocol,
    )
    assert parsed["audit_valid"] is True
    lifecycle = probe.evaluate_support_lifecycle(
        parsed["samples"],
        [_state(0.0), _state(0.0), _state(0.01)],
        protocol=protocol,
    )

    assert lifecycle["audit_valid"] is True
    assert lifecycle["support_valid"] is True
    assert lifecycle["states"] == ["CURRENT", "CURRENT", "LOST"]
    assert lifecycle["loss_index"] == 2


def test_v3_does_not_credit_partial_loss_or_an_omitted_active_support_pair():
    protocol = _v3_protocol()
    identities = _identities(
        support_colliders=[SUPPORT, TABLE_SUPPORT],
        other_colliders=[],
    )
    found_both = _composite_support_contact_report(
        ("FOUND", SUPPORT, 1),
        ("FOUND", TABLE_SUPPORT, 1),
    )
    cube_lost_table_current = _composite_support_contact_report(
        ("LOST", SUPPORT, 0),
        ("PERSIST", TABLE_SUPPORT, 1),
    )
    parsed = probe.evaluate_contact_trace(
        [found_both, cube_lost_table_current],
        identities=identities,
        geometry=[_geometry(), _geometry()],
        protocol=protocol,
    )
    lifecycle = probe.evaluate_support_lifecycle(
        parsed["samples"],
        [_state(0.0), _state(0.0)],
        protocol=protocol,
    )
    assert lifecycle["audit_valid"] is True
    assert lifecycle["support_valid"] is False
    assert "support_lost_missing" in lifecycle["physical_failures"]

    accumulator = probe.ContactLifecycleAccumulator(identities, protocol=protocol)
    accumulator.consume(physics_index=0, raw=found_both)
    with pytest.raises(probe.ContactAuditError, match="contact_active_pair_missing"):
        accumulator.consume(physics_index=1, raw=_empty_contact_report())


def test_v3_allows_table_only_late_initial_persist_but_not_a_new_table_support_after_close():
    protocol = _v3_protocol()
    identities = _identities(
        support_colliders=[SUPPORT, TABLE_SUPPORT],
        other_colliders=[],
    )
    parser = probe.ContactLifecycleAccumulator(identities, protocol=protocol)
    observer = probe.SupportObserverAccumulator(protocol=protocol)
    for index in range(10):
        sample = parser.consume(physics_index=index, raw=_empty_contact_report())
        assert observer.consume(
            sample,
            source_state=_state(0.0),
            transition_index=index,
        )["state"] == "UNOBSERVED"
    table_initial = parser.consume(
        physics_index=10,
        raw=_support_contact_report("PERSIST", support=TABLE_SUPPORT),
    )
    assert observer.consume(
        table_initial,
        source_state=_state(0.0),
        transition_index=10,
    )["state"] == "CURRENT"

    reports = [
        _support_contact_report("FOUND"),
        _composite_support_contact_report(
            ("PERSIST", SUPPORT, 1),
            ("FOUND", TABLE_SUPPORT, 1),
        ),
    ]
    parsed = probe.evaluate_contact_trace(
        reports,
        identities=identities,
        geometry=[_geometry(), _geometry()],
        protocol=protocol,
    )
    lifecycle = probe.evaluate_support_lifecycle(
        parsed["samples"],
        [_state(0.0), _state(0.0)],
        protocol=protocol,
        action_contexts=[
            {
                "pick_event": 4,
                "action": {"joint_positions": [0.0] * 9},
                "apply_count": 1,
                "action_receipt": {"applied": True, "normal_return": True, "apply_count": 1},
            },
            {"pick_event": None, "action": None, "apply_count": 0, "action_receipt": None},
        ],
    )
    assert lifecycle["audit_valid"] is True
    assert lifecycle["support_valid"] is False
    assert "late_support_pair_after_close" in lifecycle["physical_failures"]


def test_v3_static_support_audit_rejects_a_disabled_or_dynamic_table_surface():
    baseline = {
        SUPPORT: _static_support_snapshot(SUPPORT),
        TABLE_SUPPORT: _static_support_snapshot(TABLE_SUPPORT),
    }
    accepted = probe.evaluate_static_support_immutability(
        baseline,
        [copy.deepcopy(baseline)],
        [],
        support_paths=[SUPPORT, TABLE_SUPPORT],
    )
    assert accepted["audit_valid"] is True
    fingerprints = {
        path: probe._static_support_boundary_fingerprint(snapshot)
        for path, snapshot in baseline.items()
    }
    assert probe.evaluate_static_support_boundary_fingerprints(
        baseline,
        [fingerprints],
        support_paths=[SUPPORT, TABLE_SUPPORT],
    )["audit_valid"] is True
    changed_fingerprint = copy.deepcopy(fingerprints)
    changed_fingerprint[TABLE_SUPPORT]["sha256"] = "0" * 64
    assert probe.evaluate_static_support_boundary_fingerprints(
        baseline,
        [changed_fingerprint],
        support_paths=[SUPPORT, TABLE_SUPPORT],
    )["audit_valid"] is False

    disabled = copy.deepcopy(baseline)
    disabled[TABLE_SUPPORT]["collision_properties"]["enabled"] = False
    rejected_disabled = probe.evaluate_static_support_immutability(
        baseline,
        [disabled],
        [],
        support_paths=[SUPPORT, TABLE_SUPPORT],
    )
    assert rejected_disabled["audit_valid"] is False

    dynamic = copy.deepcopy(baseline)
    dynamic[TABLE_SUPPORT]["ancestor_body_state"] = {
        "/World/table": {
            "rigid_body_api": True,
            "rigid_body_enabled": True,
            "kinematic_enabled": False,
        }
    }
    rejected_dynamic = probe.evaluate_static_support_immutability(
        baseline,
        [dynamic],
        [],
        support_paths=[SUPPORT, TABLE_SUPPORT],
    )
    assert rejected_dynamic["audit_valid"] is False


def test_v3_physical_evaluator_requires_terminal_loss_for_both_support_pairs():
    protocol = _v3_protocol()
    trace = _passing_trace()
    for index, transition in enumerate(trace):
        lost = index >= 12
        transition["contact"].update(
            {
                "initial_support_absent_reports": 0,
                "initial_support_prefix_physical_failures": [],
                "support_pair_physical_failures": [],
                "support_pairs": [
                    {
                        "pair": sorted((SOURCE, SUPPORT)),
                        "ever_current": True,
                        "current": not lost,
                        "terminal_lost": lost,
                    },
                    {
                        "pair": sorted((SOURCE, TABLE_SUPPORT)),
                        "ever_current": True,
                        "current": not lost,
                        "terminal_lost": lost,
                    },
                ],
            }
        )
    accepted = probe.evaluate_native_lift_pour_trace(
        trace,
        retention_steps=60,
        rise_threshold_m=0.12,
        initial_support_activation_max_absent_reports=10,
        protocol=protocol,
    )
    assert accepted["physical_passed"] is True

    incomplete = copy.deepcopy(trace)
    incomplete[12]["contact"]["support_pairs"][1]["terminal_lost"] = False
    rejected = probe.evaluate_native_lift_pour_trace(
        incomplete,
        retention_steps=60,
        rise_threshold_m=0.12,
        initial_support_activation_max_absent_reports=10,
        protocol=protocol,
    )
    assert rejected["physical_passed"] is False
    assert "support_pairs_loss_incomplete" in rejected["physical_failures"]


@pytest.mark.parametrize("event", ["FOUND", "PERSIST"])
def test_v2_support_observer_allows_only_ten_absent_reports_then_a_current_support_activation(event):
    frozen = probe.freeze_diagnostic_config(
        V2_CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )
    protocol = probe.resolve_protocol_spec(frozen["config"])
    observer, entries = _observer_entries(
        [_empty_contact_report() for _index in range(10)]
        + [_support_contact_report(event)],
        protocol,
    )

    assert [entry["observer"]["state"] for entry in entries[:10]] == ["UNOBSERVED"] * 10
    assert [entry["observer"]["absent_reports"] for entry in entries[:10]] == list(
        range(1, 11)
    )
    assert all(entry["observer"]["audit_no_go_code"] is None for entry in entries)
    assert entries[-1]["observer"] == {
        "state_before": "UNOBSERVED",
        "state": "CURRENT",
        "absent_reports_before": 10,
        "absent_reports": 10,
        "activation_event": event,
        "audit_no_go_code": None,
        "prefix_physical_failures": [],
    }
    assert observer.state == "CURRENT"


def test_v1_first_absent_report_remains_an_audit_no_go_while_v2_rejects_the_eleventh():
    v1 = probe.resolve_protocol_spec(
        probe.freeze_diagnostic_config(
            CONFIG_PATH,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )["config"]
    )
    _observer, v1_entries = _observer_entries([_empty_contact_report()], v1)
    assert v1_entries[0]["observer"]["audit_no_go_code"] == "support_initial_state_unknown"

    v2 = probe.resolve_protocol_spec(
        probe.freeze_diagnostic_config(
            V2_CONFIG_PATH,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )["config"]
    )
    _observer, v2_entries = _observer_entries(
        [_empty_contact_report() for _index in range(11)], v2
    )
    assert v2_entries[-1]["observer"] == {
        "state_before": "UNOBSERVED",
        "state": "UNOBSERVED",
        "absent_reports_before": 10,
        "absent_reports": 10,
        "activation_event": None,
        "audit_no_go_code": "support_initial_activation_timeout",
        "prefix_physical_failures": [],
    }


def test_v2_support_activation_requires_a_nonempty_current_source_cube_manifold():
    protocol = probe.resolve_protocol_spec(
        probe.freeze_diagnostic_config(
            V2_CONFIG_PATH,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )["config"]
    )
    _observer, entries = _observer_entries(
        [_empty_contact_report() for _index in range(10)]
        + [_support_contact_report("PERSIST", contact_count=0)],
        protocol,
    )

    assert entries[-1]["observer"]["state"] == "UNOBSERVED"
    assert entries[-1]["observer"]["audit_no_go_code"] == "support_current_contact_missing"


@pytest.mark.parametrize(
    "report, expected_failure",
    [
        (
            {
                "headers": [_header("FOUND", SOURCE, LEFT, contact_offset=0, contact_count=1)],
                "contact_data": [_point((-1.0, 0.0, 5.0), (1.0, 0.0, 0.0))],
                "friction_anchors": [],
            },
            "initial_observer_source_finger_contact",
        ),
        (
            {
                "headers": [_header("FOUND", SOURCE, HAND, contact_offset=0, contact_count=1)],
                "contact_data": [_point((0.0, 0.0, 5.0), (1.0, 0.0, 0.0))],
                "friction_anchors": [],
            },
            "initial_observer_forbidden_source_contact",
        ),
        (
            {
                "headers": [_header("FOUND", LEFT, SUPPORT, contact_offset=0, contact_count=1)],
                "contact_data": [_point((-1.0, 0.0, 5.0), (1.0, 0.0, 0.0))],
                "friction_anchors": [],
            },
            "initial_observer_robot_environment_contact",
        ),
    ],
)
def test_v2_pending_prefix_latches_observed_non_support_contacts(report, expected_failure):
    protocol = probe.resolve_protocol_spec(
        probe.freeze_diagnostic_config(
            V2_CONFIG_PATH,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )["config"]
    )
    _observer, entries = _observer_entries([report], protocol)

    assert entries[0]["observer"]["state"] == "UNOBSERVED"
    assert entries[0]["observer"]["audit_no_go_code"] is None
    assert entries[0]["observer"]["prefix_physical_failures"] == [expected_failure]


def test_v2_event_four_closes_the_observer_activation_window_without_altering_action_application():
    protocol = probe.resolve_protocol_spec(
        probe.freeze_diagnostic_config(
            V2_CONFIG_PATH,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )["config"]
    )
    observer, entries = _observer_entries([_empty_contact_report()], protocol)
    missing = observer.observe_action(
        pick_event=4,
        action={"joint_positions": [0.0] * 9},
        apply_count=1,
        action_receipt={"applied": True, "normal_return": True, "apply_count": 1},
    )
    assert entries[0]["observer"]["state"] == "UNOBSERVED"
    assert missing == {"audit_no_go_code": "support_activation_before_close_missing"}

    active_observer, _entries = _observer_entries([_support_contact_report("FOUND")], protocol)
    assert active_observer.observe_action(
        pick_event=4,
        action={"joint_positions": [0.0] * 9},
        apply_count=1,
        action_receipt={"applied": True, "normal_return": True, "apply_count": 1},
        classifications=["SOURCE_OTHER"],
    ) == {"audit_no_go_code": None}
    assert active_observer.prefix_physical_failures == [
        "initial_observer_forbidden_source_contact"
    ]
    assert active_observer.observe_action(
        pick_event=4,
        action=None,
        apply_count=0,
        action_receipt=None,
    ) == {"audit_no_go_code": "support_activation_close_action_invalid"}


def test_v2_event_four_latches_same_step_forbidden_contact_as_a_physical_failure():
    protocol = probe.resolve_protocol_spec(
        probe.freeze_diagnostic_config(
            V2_CONFIG_PATH,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )["config"]
    )
    activation = _support_contact_report("FOUND")
    activation["headers"].append(
        _header("FOUND", SOURCE, HAND, contact_offset=1, contact_count=1)
    )
    activation["contact_data"].append(
        _point((0.0, 0.0, 5.0), (1.0, 0.0, 0.0))
    )
    contacts = probe.evaluate_contact_trace(
        [_empty_contact_report(), activation],
        identities=_identities(),
        geometry=[_geometry(), _geometry()],
        protocol=protocol,
    )
    lifecycle = probe.evaluate_support_lifecycle(
        contacts["samples"],
        [_state(0.0), _state(0.0)],
        protocol=protocol,
        action_contexts=[
            {"pick_event": None, "action": None, "apply_count": 0, "action_receipt": None},
            {
                "pick_event": 4,
                "action": {"joint_positions": [0.0] * 9},
                "apply_count": 1,
                "action_receipt": {"applied": True, "normal_return": True, "apply_count": 1},
            },
        ],
    )

    assert lifecycle["audit_valid"] is True
    assert lifecycle["support_valid"] is False
    assert "initial_observer_forbidden_source_contact" in lifecycle["physical_failures"]


def test_v2_initial_support_failure_evidence_is_deep_copied_and_replayed():
    protocol = probe.resolve_protocol_spec(
        probe.freeze_diagnostic_config(
            V2_CONFIG_PATH,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )["config"]
    )
    _observer, entries = _observer_entries(
        [_empty_contact_report() for _index in range(11)], protocol
    )
    evidence = probe.build_initial_support_failure_evidence(
        protocol=protocol,
        code="support_initial_activation_timeout",
        observations=entries,
    )
    entries[0]["raw_report"]["headers"].append(
        _header("FOUND", SOURCE, SUPPORT, contact_offset=0, contact_count=0)
    )

    assert evidence["observations"][0]["raw_report"] == _empty_contact_report()
    assert probe.validate_initial_support_failure_evidence(
        evidence,
        identities=_identities(),
        protocol=protocol,
    ) == {
        "audit_valid": True,
        "audit_failures": [],
        "failure_code": "support_initial_activation_timeout",
    }

    tampered = copy.deepcopy(evidence)
    tampered["observations"][5]["observer"]["absent_reports"] = 7
    rejected = probe.validate_initial_support_failure_evidence(
        tampered,
        identities=_identities(),
        protocol=protocol,
    )
    assert rejected["audit_valid"] is False
    assert "initial_support_failure_observer_mismatch" in rejected["audit_failures"]


def test_v2_event_four_failure_evidence_replays_the_applied_action_context():
    protocol = probe.resolve_protocol_spec(
        probe.freeze_diagnostic_config(
            V2_CONFIG_PATH,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )["config"]
    )
    observer, entries = _observer_entries([_empty_contact_report()], protocol)
    gate = observer.observe_action(
        pick_event=4,
        action={"joint_positions": [0.0] * 9},
        apply_count=1,
        action_receipt={"applied": True, "normal_return": True, "apply_count": 1},
        classifications=[],
    )
    entries[0]["action_context"] = {
        "pick_event": 4,
        "action": {"joint_positions": [0.0] * 9},
        "apply_count": 1,
        "action_receipt": {"applied": True, "normal_return": True, "apply_count": 1},
        "close_gate": gate,
    }
    evidence = probe.build_initial_support_failure_evidence(
        protocol=protocol,
        code="support_activation_before_close_missing",
        observations=entries,
    )

    assert probe.validate_initial_support_failure_evidence(
        evidence,
        identities=_identities(),
        protocol=protocol,
    )["audit_valid"] is True


def test_v2_pending_prefix_cannot_receive_physical_pass_credit():
    trace = _passing_trace()
    close_fields = {
        name: copy.deepcopy(trace[0][name])
        for name in (
            "action",
            "canonical_action",
            "apply_count",
            "action_receipt",
            "integrating_transition_index",
        )
    }
    for name, value in close_fields.items():
        trace[1][name] = value
    trace[1]["pick_event"] = 4
    trace[1]["integrating_transition_index"] = 2
    trace[0].update(
        {
            "action": None,
            "canonical_action": None,
            "apply_count": 0,
            "action_receipt": None,
            "integrating_transition_index": None,
            "pick_event": None,
        }
    )
    trace[0]["contact"].update(
        {
            "support_state": "UNOBSERVED",
            "support_event": None,
            "support_header_count": 0,
            "support_contact_count": 0,
            "support_friction_anchor_count": 0,
            "initial_support_absent_reports": 1,
            "initial_support_prefix_physical_failures": [
                "initial_observer_forbidden_source_contact"
            ],
        }
    )
    trace[1]["contact"]["initial_support_prefix_physical_failures"] = [
        "initial_observer_forbidden_source_contact"
    ]

    result = probe.evaluate_native_lift_pour_trace(
        trace,
        retention_steps=60,
        rise_threshold_m=0.12,
        initial_support_activation_max_absent_reports=10,
    )
    assert result["audit_valid"] is True
    assert result["physical_passed"] is False
    assert "initial_observer_forbidden_source_contact" in result["physical_failures"]


def test_parent_replay_rejects_a_tampered_v2_observer_projection():
    protocol = probe.resolve_protocol_spec(
        probe.freeze_diagnostic_config(
            V2_CONFIG_PATH,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )["config"]
    )
    reports = [
        _empty_contact_report(),
        _support_contact_report("FOUND"),
        {
            "headers": [_header("LOST", SOURCE, SUPPORT, contact_offset=0, contact_count=0)],
            "contact_data": [],
            "friction_anchors": [],
        },
    ]
    for index, report in enumerate(reports):
        report.update(
            {
                "physics_index": index,
                "immediate_read_index": index,
                "immediate_read_count": index + 1,
            }
        )
    contacts = probe.evaluate_contact_trace(
        reports,
        identities=_identities(),
        geometry=[_geometry() for _index in reports],
        require_immediate_read=True,
        protocol=protocol,
    )
    lifecycle = probe.evaluate_support_lifecycle(
        contacts["samples"],
        [_state(0.0), _state(0.0), _state(0.0)],
        protocol=protocol,
        action_contexts=[
            {"pick_event": None, "action": None, "apply_count": 0, "action_receipt": None}
            for _index in reports
        ],
    )
    transitions = []
    for index, (report, sample, decision) in enumerate(
        zip(reports, contacts["samples"], lifecycle["decisions"])
    ):
        summary = probe._runtime_contact_summary(
            sample,
            source_awake=True,
            observer_decision=decision,
        )
        summary["source_support_recontact"] = False
        transitions.append(
            {
                "post": _state(0.0),
                "pick_event": None,
                "action": None,
                "apply_count": 0,
                "action_receipt": None,
                "contact": {
                    "raw_report": copy.deepcopy(report),
                    "geometry": _geometry(),
                    **summary,
                },
            }
        )
    evidence = {"contact_identities": _identities(), "protocol": protocol}

    accepted = probe._parent_recompute_instrumented_contacts(transitions, evidence)
    assert accepted["audit_valid"] is True

    v1_protocol = probe.resolve_protocol_spec(
        probe.freeze_diagnostic_config(
            CONFIG_PATH,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )["config"]
    )
    wrong_protocol = probe._parent_recompute_instrumented_contacts(
        transitions,
        evidence,
        protocol=v1_protocol,
    )
    assert wrong_protocol == {
        "audit_valid": False,
        "audit_failures": ["instrumented_protocol_binding_mismatch"],
    }

    tampered = copy.deepcopy(transitions)
    tampered[1]["contact"]["initial_support_absent_reports"] = 9
    rejected = probe._parent_recompute_instrumented_contacts(tampered, evidence)
    assert rejected["audit_valid"] is False
    assert rejected["audit_failures"] == ["instrumented_contact_replay_mismatch"]


@pytest.mark.parametrize("alteration", ["wrong", "missing"])
def test_freeze_rejects_wrong_or_missing_local_franka_hash(alteration, tmp_path):
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    local_franka = config["diagnostic"]["local_franka"]
    if alteration == "wrong":
        local_franka["sha256"] = "0" * 64
    else:
        local_franka.pop("sha256")
    altered = tmp_path / f"local-franka-{alteration}.yaml"
    altered.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(ValueError, match="native_unbound_local_franka"):
        probe.freeze_diagnostic_config(
            altered,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )


@pytest.mark.parametrize(
    "local_scene",
    [
        {"usd_path": LOCAL_SCENE_USD_PATH, "sha256": "0" * 64},
        {"usd_path": "../outside.usd", "sha256": LOCAL_SCENE_SHA256},
        {"usd_path": LOCAL_SCENE_USD_PATH},
    ],
)
def test_local_scene_requires_the_pinned_localized_raw_asset(local_scene):
    with pytest.raises(ValueError, match="native_unbound_local_scene"):
        probe.resolve_local_scene_asset({"local_scene": local_scene})

    resolved = probe.resolve_local_scene_asset(
        {
            "local_scene": {
                "usd_path": LOCAL_SCENE_USD_PATH,
                "sha256": LOCAL_SCENE_SHA256,
            }
        }
    )
    assert resolved == {
        "usd_path": LOCAL_SCENE_USD_PATH,
        "absolute_usd_path": str((REPO_ROOT / LOCAL_SCENE_USD_PATH).resolve()),
        "sha256": LOCAL_SCENE_SHA256,
    }


def test_diagnostic_local_franka_path_is_forwarded_explicitly_to_create_robot():
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    config["robot"]["usd_path"] = "omniverse://remote/default/franka.usd"
    local_franka = probe.resolve_local_franka_asset(config["diagnostic"])
    calls = []
    sentinel = object()

    def create_robot(robot_type, **kwargs):
        calls.append((robot_type, kwargs))
        return sentinel

    robot = probe.create_diagnostic_local_franka(
        create_robot,
        config,
        local_franka=local_franka,
    )

    assert robot is sentinel
    assert len(calls) == 1
    robot_type, kwargs = calls[0]
    assert robot_type == "franka"
    assert set(kwargs) == {"position", "usd_path"}
    assert kwargs["position"].tolist() == [-0.4, 0.0, 0.71]
    assert kwargs["usd_path"] == local_franka["absolute_usd_path"]
    assert Path(kwargs["usd_path"]).is_absolute()
    assert "omniverse://" not in kwargs["usd_path"]


def test_frozen_config_keeps_local_franka_diagnostic_and_builds_current_source_contract():
    frozen = probe.freeze_diagnostic_config(
        CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )
    production = yaml.safe_load(PRODUCTION_CONFIG_PATH.read_text(encoding="utf-8"))
    projection = probe.production_visible_projection(frozen["config"])
    calls = []
    sentinel = object()

    def create_robot(robot_type, **kwargs):
        calls.append((robot_type, kwargs))
        return sentinel

    robot = probe.create_diagnostic_local_franka(
        create_robot,
        frozen["config"],
        local_franka=frozen["local_franka"],
    )

    assert frozen["config"]["diagnostic"]["local_franka"] == {
        "usd_path": LOCAL_FRANKA_USD_PATH,
        "sha256": LOCAL_FRANKA_SHA256,
    }
    assert "diagnostic" not in projection
    assert projection == probe.production_visible_projection(production)
    assert robot is sentinel
    assert len(calls) == 1
    robot_type, kwargs = calls[0]
    assert robot_type == frozen["config"]["robot"]["type"]
    assert set(kwargs) == {"position", "usd_path"}
    assert kwargs["position"].tolist() == frozen["config"]["robot"]["position"]
    assert kwargs["usd_path"] == frozen["local_franka"]["absolute_usd_path"]

    source_contract = _dynamic_source_contract(
        scene_owner=None,
        simulation_owner_targets=[],
    )
    assert probe.evaluate_dynamic_source_contract(source_contract) == {
        "audit_valid": True,
        "physical_valid": True,
        "audit_failures": [],
        "physical_failures": [],
    }


def test_local_franka_evidence_rejects_remote_prim_stack_identity():
    identity = _local_franka_runtime_identity(
        prim_stack_layers=[
            {
                "identifier": "omniverse://remote/FrankaPanda/franka.usd",
                "real_path": str((REPO_ROOT / LOCAL_FRANKA_USD_PATH).resolve()),
                "sha256": LOCAL_FRANKA_SHA256,
            }
        ]
    )
    config = probe.freeze_diagnostic_config(
        CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )["config"]

    result = probe.evaluate_local_franka_evidence(
        identity,
        copy.deepcopy(identity),
        diagnostic=config["diagnostic"],
    )

    assert result["audit_valid"] is False
    assert "local_franka_remote_dependency" in result["audit_failures"]


def test_local_franka_allows_only_the_pinned_isaac_runtime_omnipbr():
    runtime_mdl = Path(probe.ISAACSIM41_FRANKA_RUNTIME_OMNIPBR_PATH)
    assert runtime_mdl.is_file()
    assert probe.sha256_file(runtime_mdl) == probe.ISAACSIM41_FRANKA_RUNTIME_OMNIPBR_SHA256
    root = (REPO_ROOT / LOCAL_FRANKA_USD_PATH).resolve()
    identity = _local_franka_runtime_identity(
        closure_files=[
            {
                "path": str(root),
                "byte_count": root.stat().st_size,
                "sha256": LOCAL_FRANKA_SHA256,
            },
            {
                "path": str(runtime_mdl),
                "byte_count": runtime_mdl.stat().st_size,
                "sha256": probe.ISAACSIM41_FRANKA_RUNTIME_OMNIPBR_SHA256,
            },
        ]
    )
    config = probe.freeze_diagnostic_config(
        CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )["config"]
    assert probe.evaluate_local_franka_evidence(
        identity,
        copy.deepcopy(identity),
        diagnostic=config["diagnostic"],
    )["audit_valid"] is True

    external = Path(sys.executable).resolve()
    rejected = _local_franka_runtime_identity(
        closure_files=[
            {
                "path": str(root),
                "byte_count": root.stat().st_size,
                "sha256": LOCAL_FRANKA_SHA256,
            },
            {
                "path": str(external),
                "byte_count": external.stat().st_size,
                "sha256": probe.sha256_file(external),
            },
        ]
    )
    result = probe.evaluate_local_franka_evidence(
        rejected,
        copy.deepcopy(rejected),
        diagnostic=config["diagnostic"],
    )
    assert result["audit_valid"] is False
    assert "local_franka_dependency_path_invalid" in result["audit_failures"]


def test_local_franka_closure_drift_and_parent_binding_are_rejected():
    config = probe.freeze_diagnostic_config(
        CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )["config"]
    pre = _local_franka_runtime_identity(
        closure_files=[
            {
                "path": str((REPO_ROOT / LOCAL_FRANKA_USD_PATH).resolve()),
                "byte_count": (REPO_ROOT / LOCAL_FRANKA_USD_PATH).stat().st_size,
                "sha256": LOCAL_FRANKA_SHA256,
            },
            {
                "path": str((REPO_ROOT / "assets/robots/SubUSDs/panda_link0.usd").resolve()),
                "byte_count": (REPO_ROOT / "assets/robots/SubUSDs/panda_link0.usd").stat().st_size,
                "sha256": probe.sha256_file(
                    REPO_ROOT / "assets/robots/SubUSDs/panda_link0.usd"
                ),
            },
        ]
    )
    post = _local_franka_runtime_identity()
    local_evidence = probe.evaluate_local_franka_evidence(
        pre,
        post,
        diagnostic=config["diagnostic"],
    )
    assert local_evidence["audit_valid"] is False
    assert "local_franka_pre_post_mismatch" in local_evidence["audit_failures"]

    parent_identity = probe.build_parent_identity(config)
    runtime_identity = {
        "config_sha256": parent_identity["config_sha256"],
        "parent_static_identity_sha256": parent_identity["identity_sha256"],
        "dependency_entry_sha256": parent_identity["asset_dependency_closure"][
            "entry_sha256"
        ],
        "local_franka_root_usd_path": LOCAL_FRANKA_USD_PATH,
        "local_franka_root_sha256": "0" * 64,
        "local_franka_dependency_closure_sha256": pre["dependency_closure"]["sha256"],
    }
    runtime_identity["sha256"] = probe._canonical_json_sha256(runtime_identity)
    evidence = {
        "child_static_identity_pre": parent_identity,
        "child_static_identity_post": copy.deepcopy(parent_identity),
        "runtime_identity_pre": runtime_identity,
        "runtime_identity_post": copy.deepcopy(runtime_identity),
        "dependency_closure": {
            "entry_sha256": parent_identity["asset_dependency_closure"]["entry_sha256"]
        },
        "post_dependency_closure": {
            "entry_sha256": parent_identity["asset_dependency_closure"]["entry_sha256"]
        },
        "local_franka": pre,
        "post_local_franka": copy.deepcopy(pre),
    }

    binding = probe.evaluate_parent_child_identity_binding(
        evidence,
        parent_identity=parent_identity,
        expected_config_sha256=parent_identity["config_sha256"],
    )
    assert binding["audit_valid"] is False
    assert "local_franka_runtime_binding_mismatch" in binding["audit_failures"]


def test_parent_is_isaac_free_and_child_command_is_exact(tmp_path):
    tree = ast.parse(Path(probe.__file__).read_text(encoding="utf-8"))
    roots = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    assert roots.isdisjoint({"isaacsim", "omni", "pxr", "carb"})

    source = Path(probe.__file__).read_text(encoding="utf-8")
    assert "main.py" not in source
    assert "online_fluid" not in source
    assert source.index("def _run_runtime_child") < source.index(
        "from factories.robot_factory import create_robot"
    )
    command = probe.build_child_command(
        treatment="control",
        frozen_config_path=tmp_path / "frozen_config.json",
        treatment_dir=tmp_path / "control",
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
        str((tmp_path / "frozen_config.json").resolve()),
        "--out-dir",
        str((tmp_path / "control").resolve()),
        "--run-nonce",
        "nonce-1",
        "--parent-pid",
        "1234",
        "--expected-config-sha256",
        "a" * 64,
    ]


def test_runtime_diagnostics_are_opt_in_and_preserve_phase_errors(monkeypatch):
    monkeypatch.delenv(probe.RUNTIME_DIAGNOSTICS_ENV, raising=False)
    assert probe.runtime_diagnostics_enabled() is False
    stream = io.StringIO()
    disabled = probe._RuntimeDiagnosticEmitter(
        enabled=False,
        stream=stream,
        pid=123,
        clock=lambda: 7.25,
    )
    with disabled.phase("trajectory.execute"):
        pass
    assert stream.getvalue() == ""

    monkeypatch.setenv(probe.RUNTIME_DIAGNOSTICS_ENV, "1")
    assert probe.runtime_diagnostics_enabled() is True
    enabled = probe._RuntimeDiagnosticEmitter(
        stream=stream,
        pid=123,
        clock=lambda: 7.25,
    )
    with enabled.phase("trajectory.execute"):
        pass
    with pytest.raises(LookupError, match="blocked"):
        with enabled.phase("finalization.trace.publish"):
            raise LookupError("blocked")

    assert stream.getvalue().splitlines() == [
        "native_unbound_runtime_diagnostic phase=trajectory.execute "
        "event=begin pid=123 monotonic_s=7.250000",
        "native_unbound_runtime_diagnostic phase=trajectory.execute "
        "event=end pid=123 monotonic_s=7.250000",
        "native_unbound_runtime_diagnostic phase=finalization.trace.publish "
        "event=begin pid=123 monotonic_s=7.250000",
        "native_unbound_runtime_diagnostic phase=finalization.trace.publish "
        "event=error:LookupError pid=123 monotonic_s=7.250000",
    ]


def test_runtime_diagnostic_stack_dump_requires_ready_handler(monkeypatch, tmp_path):
    class FaultHandler:
        def __init__(self):
            self.calls = []

        def register(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    stream = io.StringIO()
    diagnostics = probe._RuntimeDiagnosticEmitter(
        enabled=True,
        stream=stream,
        pid=456,
        clock=lambda: 1.0,
    )
    handler = FaultHandler()
    assert probe.install_runtime_diagnostic_stack_dump(
        diagnostics,
        faulthandler_module=handler,
    ) is True
    assert handler.calls == [
        ((probe.signal.SIGUSR1,), {"file": stream, "all_threads": True, "chain": False})
    ]
    assert "event=stack_dump_handler_ready" in stream.getvalue()

    stderr_path = tmp_path / "child.stderr.log"
    stderr_path.write_text(stream.getvalue(), encoding="utf-8")

    class RunningProcess:
        pid = 789

        def poll(self):
            return None

    signals = []
    pauses = []
    monkeypatch.setattr(
        probe.os,
        "kill",
        lambda pid, signum: signals.append((pid, signum)),
    )
    assert probe.request_runtime_diagnostic_stack_dump(
        RunningProcess(),
        diagnostics_enabled=True,
        stderr_path=stderr_path,
        grace_seconds=0.5,
        sleep=lambda seconds: pauses.append(seconds),
    ) is True
    assert signals == [(789, probe.signal.SIGUSR1)]
    assert pauses == [0.5]

    assert probe.request_runtime_diagnostic_stack_dump(
        RunningProcess(),
        diagnostics_enabled=False,
        stderr_path=stderr_path,
        grace_seconds=0.5,
        sleep=lambda _seconds: pytest.fail("disabled diagnostics must not sleep"),
    ) is False

    stderr_path.write_text("not-ready\n", encoding="utf-8")
    assert probe.request_runtime_diagnostic_stack_dump(
        RunningProcess(),
        diagnostics_enabled=True,
        stderr_path=stderr_path,
        grace_seconds=0.5,
        sleep=lambda _seconds: pytest.fail("unready diagnostics must not sleep"),
    ) is False

    runtime_child_source = inspect.getsource(probe._run_runtime_child)
    assert 'diagnostics.phase("application.close")' in runtime_child_source


def test_contact_path_resolution_failure_names_the_unresolved_header_field():
    class Header:
        type = 0
        stage_id = 7
        actor0 = 0

    class Interface:
        @staticmethod
        def get_full_contact_report():
            return [Header()], [], []

    reporter = probe._RuntimeFullContactReporter(
        simulation_interface=Interface(),
        resolve_path=lambda value: "" if value == 0 else f"/World/{value}",
    )

    with pytest.raises(probe.AuditNoGo, match="contact_path_resolution_failed:actor0:0") as error:
        reporter.sample(physics_index=0)
    assert error.value.evidence == {"field": "actor0", "identifier": 0}


def test_contact_material_identifier_zero_is_recorded_without_relaxing_actor_identity():
    class Header:
        type = 0
        stage_id = 7
        actor0 = 1
        actor1 = 2
        collider0 = 3
        collider1 = 4
        proto_index0 = 0xFFFFFFFF
        proto_index1 = 0xFFFFFFFF
        contact_data_offset = 0
        num_contact_data = 1
        friction_anchors_offset = 0
        num_friction_anchors_data = 0

    class Point:
        position = [0.0, 0.0, 0.0]
        normal = [0.0, 0.0, 1.0]
        impulse = [0.0, 0.0, 0.0]
        separation = -0.001
        face_index0 = 0
        face_index1 = 0
        material0 = 0
        material1 = 5

    class Interface:
        @staticmethod
        def get_full_contact_report():
            return [Header()], [Point()], []

    reporter = probe._RuntimeFullContactReporter(
        simulation_interface=Interface(),
        resolve_path=lambda value: f"/World/{value}",
    )
    report = reporter.sample(physics_index=0)

    assert report["contact_data"][0]["material0"] == probe.CONTACT_MATERIAL_IDENTIFIER_ZERO
    assert report["contact_data"][0]["material1"] == "/World/5"


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({}, "NATIVE_EXPERT_UNBOUND_LIFT_PASS"),
        ({"physical_passed": False}, "NATIVE_EXPERT_UNBOUND_LIFT_FAIL"),
        ({"audit_no_go": True}, "NATIVE_EXPERT_UNBOUND_AUDIT_NO_GO"),
        ({"runtime_error": True}, "PROBE_RUNTIME_ERROR"),
        (
            {"runtime_error": True, "audit_no_go": True, "physical_passed": False},
            "PROBE_RUNTIME_ERROR",
        ),
    ],
)
def test_final_decision_precedence_is_fixed(changes, expected):
    assert probe.select_decision(_components(**changes)) == expected


def test_strict_create_only_artifacts_never_replace_or_accept_nonfinite(tmp_path):
    path = tmp_path / "report.json"
    probe.atomic_create_json(path, {"value": 1.0})
    assert probe.load_strict_json_object(path) == {"value": 1.0}
    with pytest.raises(FileExistsError, match="native_unbound_output_exists"):
        probe.atomic_create_json(path, {"replacement": True})
    with pytest.raises(ValueError, match="native_unbound_json_nonfinite"):
        probe.atomic_create_json(tmp_path / "nan.json", {"value": float("nan")})

    malformed = tmp_path / "malformed.json"
    malformed.write_bytes(b'{"value":NaN}\n')
    with pytest.raises(ValueError, match="native_unbound_strict_json_invalid"):
        probe.load_strict_json_object(malformed)


def test_static_usd_nonfinite_values_use_explicit_json_safe_tags():
    tagged = probe._static_usd_native(
        {
            "finite": 1.0,
            "positive": float("inf"),
            "negative": float("-inf"),
            "nan": float("nan"),
        }
    )

    tag = probe.STATIC_USD_NONFINITE_FLOAT_TAG
    assert tagged == {
        "finite": 1.0,
        "positive": {tag: "+inf"},
        "negative": {tag: "-inf"},
        "nan": {tag: "nan"},
    }
    encoded = probe._canonical_json_bytes(tagged)
    assert json.loads(
        encoded,
        parse_constant=lambda value: pytest.fail(f"non-strict JSON constant: {value}"),
    ) == tagged


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_live_runtime_values_and_artifacts_reject_nonfinite(value, tmp_path):
    with pytest.raises(ValueError, match="native_unbound_json_nonfinite"):
        probe._runtime_native(value)
    with pytest.raises(ValueError, match="native_unbound_metric_threshold_invalid"):
        probe._finite_scalar(value, field="metric_threshold")
    with pytest.raises(ValueError, match="native_unbound_source_velocity_invalid"):
        probe._finite_vector([value, 0.0, 0.0], field="source_velocity")
    with pytest.raises(ValueError, match="native_unbound_contact_impulse_invalid"):
        probe._finite_vector([0.0, value, 0.0], field="contact_impulse")
    with pytest.raises(ValueError, match="native_unbound_json_nonfinite"):
        probe.atomic_create_json(tmp_path / "report.json", {"value": value})


def test_row_vector_normal_transform_uses_inverse_transpose_for_source_up():
    scale = 0.0005
    root_half = math.sqrt(0.5) * scale
    matrix = np.asarray(
        [
            [root_half, root_half, 0.0, 0.0],
            [0.0, 0.0, scale, 0.0],
            [root_half, -root_half, 0.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )

    assert probe._world_normal_from_local(np.asarray([0.0, 1.0, 0.0]), matrix) == pytest.approx(
        [0.0, 0.0, 1.0]
    )
    geometry = {
        "gravity_world_m_s2": [0.0, 0.0, -9.81],
        "source_reset_world_from_local": matrix.tolist(),
        "source": {"world_from_local": matrix.tolist()},
    }
    local_up, source_up = probe._source_local_up(geometry)
    assert local_up.tolist() == [0.0, 1.0, 0.0]
    assert source_up == pytest.approx([0.0, 0.0, 1.0])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_report_layer_metric_threshold_rejects_nonfinite(value):
    class PropertySpec:
        name = "physxContactReport:threshold"

        def GetInfo(self, name):
            assert name == "default"
            return value

    class PrimSpec:
        path = SOURCE
        properties = [PropertySpec()]
        nameChildren = []

        def GetInfo(self, name):
            assert name == "apiSchemas"
            return None

        def ListInfoKeys(self):
            return []

    class Layer:
        rootPrims = [PrimSpec()]

    with pytest.raises(ValueError, match="native_unbound_report_threshold_invalid"):
        probe._runtime_layer_catalog(Layer())


def test_local_franka_static_max_force_snapshot_tags_authored_infinity(monkeypatch):
    class Attribute:
        def GetName(self):
            return "physics:maxForce"

        def Get(self):
            return float("inf")

    class Prim:
        def IsValid(self):
            return True

        def GetPath(self):
            return LEFT_BODY

        def GetAppliedSchemas(self):
            return []

        def GetAttributes(self):
            return [Attribute()]

        def GetRelationships(self):
            return []

    prim = Prim()

    class Stage:
        def GetPrimAtPath(self, path):
            assert path == LEFT_BODY
            return prim

    monkeypatch.setitem(
        sys.modules,
        "pxr",
        SimpleNamespace(Usd=SimpleNamespace(PrimRange=lambda root: [root])),
    )
    monkeypatch.setattr(
        probe,
        "_runtime_material_binding",
        lambda _stage, _path: {"material_path": None, "unresolved": True},
    )

    snapshot = probe._runtime_physics_properties(Stage(), LEFT_BODY)

    assert snapshot["attributes"] == [
        {
            "path": LEFT_BODY,
            "name": "physics:maxForce",
            "value": {probe.STATIC_USD_NONFINITE_FLOAT_TAG: "+inf"},
        }
    ]
    assert json.loads(
        probe._canonical_json_bytes(snapshot),
        parse_constant=lambda value: pytest.fail(f"non-strict JSON constant: {value}"),
    ) == snapshot


def test_physics_material_snapshot_records_empty_default_and_rejects_dangling_target(
    monkeypatch,
):
    class Relationship:
        def __init__(self, name, targets):
            self._name = name
            self._targets = targets

        def GetName(self):
            return self._name

        def GetTargets(self):
            return self._targets

        def GetMetadata(self, name):
            assert name == "bindMaterialAs"
            return None

    class Prim:
        def __init__(self, relationships):
            self._relationships = relationships

        def IsValid(self):
            return True

        def GetPath(self):
            return LEFT

        def GetRelationships(self):
            return self._relationships

    class Stage:
        def __init__(self, prim):
            self._prim = prim

        def GetPrimAtPath(self, path):
            assert path == LEFT
            return self._prim

    class Binding:
        def __init__(self, prim):
            self._prim = prim

        def ComputeBoundMaterial(self, *args, **kwargs):
            assert args == ("physics",) or kwargs == {"materialPurpose": "physics"}
            return None, None

    monkeypatch.setitem(
        sys.modules,
        "pxr",
        SimpleNamespace(UsdShade=SimpleNamespace(MaterialBindingAPI=Binding)),
    )

    empty = probe._runtime_material_binding(
        Stage(Prim([Relationship("material:binding:physics", [])])), LEFT
    )
    assert empty == {
        "material_path": None,
        "relationship_name": None,
        "relationship_owner": None,
        "targets": [],
        "physics_binding_state": "authored_empty_default",
        "authored_physics_relationships": [
            {
                "owner_path": LEFT,
                "name": "material:binding:physics",
                "targets": [],
                "bind_material_as": None,
            }
        ],
    }

    visual_only = probe._runtime_material_binding(
        Stage(Prim([Relationship("material:binding", ["/World/Looks/Visual"])])), LEFT
    )
    assert visual_only["physics_binding_state"] == "no_authored_physics_default"
    assert visual_only["authored_physics_relationships"] == []

    with pytest.raises(probe.AuditNoGo, match="material_binding_unresolved"):
        probe._runtime_material_binding(
            Stage(Prim([Relationship("material:binding:physics", ["/World/Missing"])])),
            LEFT,
        )


def test_static_property_snapshot_comparison_is_deterministic_for_tagged_infinity():
    baseline = _property_snapshot()
    baseline["left_finger"] = {
        "attributes": [
            {
                "path": LEFT_BODY,
                "name": "physics:maxForce",
                "value": probe._static_usd_native(float("inf")),
            }
        ]
    }
    unchanged = copy.deepcopy(baseline)
    changed = copy.deepcopy(baseline)
    changed["left_finger"]["attributes"][0]["value"] = probe._static_usd_native(
        float("-inf")
    )

    assert probe._canonical_json_bytes(baseline) == probe._canonical_json_bytes(unchanged)
    assert probe._canonical_json_sha256(baseline) == probe._canonical_json_sha256(unchanged)
    assert probe.evaluate_source_robot_property_mutations(
        baseline, [unchanged], []
    )["audit_valid"] is True
    changed_result = probe.evaluate_source_robot_property_mutations(baseline, [changed], [])
    assert changed_result["audit_valid"] is False
    assert "source_robot_physical_properties_changed" in changed_result["audit_failures"]


def test_dynamic_source_contract_is_fail_closed():
    accepted = probe.evaluate_dynamic_source_contract(_dynamic_source_contract())
    assert accepted["audit_valid"] is True
    assert accepted["physical_valid"] is True

    sleeping = probe.evaluate_dynamic_source_contract(
        _dynamic_source_contract(awake=False)
    )
    assert sleeping["audit_valid"] is True
    assert sleeping["physical_valid"] is False

    missing_readback = _dynamic_source_contract()
    missing_readback["motion_readbacks"]["physx_is_sleeping"] = False
    rejected = probe.evaluate_dynamic_source_contract(missing_readback)
    assert rejected["audit_valid"] is False
    assert "motion_authority_missing" in rejected["audit_failures"]


def test_relation_inventory_keeps_empty_builtin_joint_slots_out_of_coupling_graph(
    monkeypatch,
):
    class Relationship:
        def __init__(self, name, targets):
            self._name = name
            self._targets = targets

        def GetName(self):
            return self._name

        def GetTargets(self):
            return self._targets

    class Joint:
        pass

    class CollisionGroup:
        pass

    class Prim:
        def __init__(self, path, relationships=(), schemas=()):
            self._path = path
            self._relationships = relationships
            self._schemas = schemas

        def GetPath(self):
            return self._path

        def IsA(self, schema):
            return schema in self._schemas

        def GetAppliedSchemas(self):
            return []

        def GetRelationships(self):
            return self._relationships

        def GetTypeName(self):
            return "PhysicsJoint" if Joint in self._schemas else "Xform"

    class Stage:
        def __init__(self, prims):
            self.prims = prims

    class PrimRange:
        @staticmethod
        def Stage(stage):
            return stage.prims

    monkeypatch.setitem(
        sys.modules,
        "pxr",
        SimpleNamespace(
            Usd=SimpleNamespace(PrimRange=PrimRange),
            UsdPhysics=SimpleNamespace(Joint=Joint, CollisionGroup=CollisionGroup),
        ),
    )
    root_joint = Prim(
        "/World/Franka/rootJoint",
        relationships=[
            Relationship("proxyPrim", []),
            Relationship("physics:body0", ["/World/Franka/panda_link0"]),
            Relationship("physics:body1", []),
        ],
        schemas=[Joint],
    )
    inventory = probe._runtime_relation_inventory(
        Stage([root_joint, Prim("/World/Franka/panda_link0")])
    )

    assert [
        (relation["owner_path"], relation["relationship"])
        for relation in inventory["relations"]
    ] == [("/World/Franka/rootJoint", "physics:body0")]
    assert {
        item["relationship"] for item in inventory["relationship_topology"]
    } == {"proxyPrim", "physics:body0", "physics:body1"}
    assert probe.evaluate_coupling_inventory(inventory)["audit_valid"] is True

    source_anchor = Prim(
        "/World/external_anchor",
        relationships=[Relationship("physics:body0", [SOURCE])],
        schemas=[Joint],
    )
    source_inventory = probe._runtime_relation_inventory(
        Stage([source_anchor, Prim(SOURCE)])
    )
    source_result = probe.evaluate_coupling_inventory(source_inventory)
    assert source_result["audit_valid"] is False
    assert "source_relation_not_explicit_static_support" in source_result["audit_failures"]


def test_coupling_evaluator_rejects_direct_transitive_and_external_source_relations():
    clean = probe.evaluate_coupling_inventory(
        {
            "relations": [
                {
                    "kind": "ordinary_static_support",
                    "endpoints": [SOURCE, SUPPORT],
                },
                {
                    "kind": "joint",
                    "endpoints": ["/World/unrelated/a", "/World/unrelated/b"],
                },
            ]
        }
    )
    assert clean["audit_valid"] is True

    direct = probe.evaluate_coupling_inventory(
        {"relations": [{"kind": "joint", "endpoints": [SOURCE, LEFT_BODY]}]}
    )
    assert direct["audit_valid"] is False
    assert "direct_source_robot_coupling" in direct["audit_failures"]

    transitive = probe.evaluate_coupling_inventory(
        {
            "relations": [
                {"kind": "constraint", "endpoints": [SOURCE, "/World/bridge"]},
                {"kind": "constraint", "endpoints": ["/World/bridge", HAND_BODY]},
            ]
        }
    )
    assert transitive["audit_valid"] is False
    assert "transitive_source_robot_coupling" in transitive["audit_failures"]

    external = probe.evaluate_coupling_inventory(
        {
            "relations": [
                {
                    "kind": "force_field_membership",
                    "endpoints": [SOURCE, "/World/ForceField"],
                }
            ]
        }
    )
    assert external["audit_valid"] is False
    assert "source_external_driving_relation" in external["audit_failures"]

    created_then_removed = probe.evaluate_coupling_inventory(
        {"relations": [], "mutation_create_remove_detected": True}
    )
    assert created_then_removed["audit_valid"] is False
    assert "coupling_create_remove_detected" in created_then_removed["audit_failures"]


def test_reset_coupling_baselines_allow_unrelated_initialization_delta():
    before_reset = {
        "relations": [
            {
                "kind": "joint",
                "endpoints": ["/World/unrelated/a", "/World/unrelated/b"],
            }
        ]
    }
    after_reset = {
        "relations": [
            *before_reset["relations"],
            {
                "kind": "generic",
                "endpoints": ["/Render/product", "/World/Camera1"],
            },
        ]
    }
    accepted = probe.evaluate_reset_coupling_inventories(before_reset, after_reset)
    assert accepted["audit_valid"] is True
    assert accepted["audit_failures"] == []

    coupled = copy.deepcopy(after_reset)
    coupled["relations"].append(
        {"kind": "attachment", "endpoints": [SOURCE, LEFT_BODY]}
    )
    rejected = probe.evaluate_reset_coupling_inventories(before_reset, coupled)
    assert rejected["audit_valid"] is False
    assert "direct_source_robot_coupling" in rejected["audit_failures"]


def test_boundary_relation_fingerprints_bind_to_a_self_hashed_reset_inventory():
    baseline = _full_relation_inventory()
    matching = {
        "schema": probe.BOUNDARY_RELATION_FINGERPRINT_SCHEMA,
        "sha256": baseline["sha256"],
    }
    accepted = probe.evaluate_relation_boundary_fingerprints(baseline, [matching])
    assert accepted == {
        "audit_valid": True,
        "audit_failures": [],
        "expected_sha256": baseline["sha256"],
    }

    changed_inventory = _full_relation_inventory(
        relation={
            "kind": "attachment",
            "owner_path": SOURCE,
            "relationship": "physics:body0",
            "endpoints": [SOURCE, LEFT_BODY],
            "identity_valid": True,
            "endpoint_partitions": {SOURCE: ["source"], LEFT_BODY: ["robot"]},
            "owner_applied_schemas": [],
            "endpoint_applied_schemas": {SOURCE: [], LEFT_BODY: []},
            "schema_resolution_complete": True,
        }
    )
    changed = probe.evaluate_relation_boundary_fingerprints(
        baseline,
        [
            {
                "schema": probe.BOUNDARY_RELATION_FINGERPRINT_SCHEMA,
                "sha256": changed_inventory["sha256"],
            }
        ],
    )
    assert changed["audit_valid"] is False
    assert changed["audit_failures"] == ["relation_inventory_changed"]

    malformed = probe.evaluate_relation_boundary_fingerprints(
        baseline,
        [{"sha256": baseline["sha256"]}],
    )
    assert malformed["audit_valid"] is False
    assert malformed["audit_failures"] == ["relation_boundary_fingerprint_invalid"]

    invalid_baseline = copy.deepcopy(baseline)
    invalid_baseline["sha256"] = "0" * 64
    rejected = probe.evaluate_relation_boundary_fingerprints(
        invalid_baseline,
        [matching],
    )
    assert rejected["audit_valid"] is False
    assert rejected["audit_failures"] == ["relation_baseline_fingerprint_invalid"]


def test_runtime_boundary_stores_a_fresh_compact_relation_fingerprint(monkeypatch):
    inventory = _full_relation_inventory()
    calls = []
    monkeypatch.setattr(
        probe,
        "_runtime_source_robot_property_snapshot",
        lambda _stage, _identities: {"source": "snapshot"},
    )
    monkeypatch.setattr(probe, "_runtime_cube_snapshot", lambda _stage: {"cube": "snapshot"})
    monkeypatch.setattr(
        probe,
        "_runtime_relation_inventory",
        lambda _stage: calls.append("sampled") or copy.deepcopy(inventory),
    )

    boundary = probe._runtime_transition_boundary(
        object(),
        identities={},
        mutation_segment={"phase": "world_step", "events": []},
        expected_relation_sha256=inventory["sha256"],
    )

    assert calls == ["sampled"]
    assert "relations" not in boundary
    assert boundary["relation_fingerprint"] == {
        "schema": probe.BOUNDARY_RELATION_FINGERPRINT_SCHEMA,
        "sha256": inventory["sha256"],
    }


def test_boundary_records_require_named_phases_and_preserve_capture_order():
    def boundary(phase):
        return {
            "mutation_segment": {"phase": phase, "events": []},
            "mutation_events": [],
            "relation_fingerprint": {
                "schema": probe.BOUNDARY_RELATION_FINGERPRINT_SCHEMA,
                "sha256": "a" * 64,
            },
        }

    boundaries = probe._boundary_records(
        [
            {
                "boundaries": {
                    "after_action": boundary("action"),
                    "after_controller": boundary("controller"),
                    "after_task": boundary("task"),
                    "after_world": boundary("world_step"),
                }
            },
            {"boundaries": {"continuation": boundary("world_step")}},
        ]
    )
    assert [item["mutation_segment"]["phase"] for item in boundaries] == [
        "world_step",
        "task",
        "controller",
        "action",
        "world_step",
    ]

    with pytest.raises(ValueError, match="native_unbound_boundary_snapshot_invalid"):
        probe._boundary_records([{"boundaries": {"after_world": boundary("world_step")}}])


def test_cube_and_source_robot_static_property_mutations_are_audit_no_go():
    cube = _cube_snapshot()
    cube_result = probe.evaluate_cube_immutability(cube, [copy.deepcopy(cube)], [])
    assert cube_result["audit_valid"] is True

    moved = copy.deepcopy(cube)
    moved["world_matrix"][3][2] = 0.001
    cube_result = probe.evaluate_cube_immutability(cube, [moved], [])
    assert cube_result["audit_valid"] is False
    assert "cube_snapshot_changed" in cube_result["audit_failures"]

    baseline = _property_snapshot()
    property_result = probe.evaluate_source_robot_property_mutations(
        baseline,
        [copy.deepcopy(baseline)],
        [],
    )
    assert property_result["audit_valid"] is True

    changed = _property_snapshot()
    changed["left_finger"]["material"] = "changed"
    property_result = probe.evaluate_source_robot_property_mutations(
        baseline,
        [changed],
        [],
    )
    assert property_result["audit_valid"] is False
    assert "source_robot_physical_properties_changed" in property_result["audit_failures"]


def test_writer_target_force_and_gripper_audit_requires_all_surfaces_and_zero_writes():
    accepted = probe.evaluate_writer_target_force_gripper_audit(_writer_audit())
    assert accepted["audit_valid"] is True

    missing = _writer_audit()
    missing["coverage"]["physics_view_forces_torques_impulses"] = False
    rejected = probe.evaluate_writer_target_force_gripper_audit(missing)
    assert rejected["audit_valid"] is False
    assert "writer_audit_coverage_incomplete" in rejected["audit_failures"]

    forced = _writer_audit()
    forced["counts"]["forces_torques_impulses"] = 1
    rejected = probe.evaluate_writer_target_force_gripper_audit(forced)
    assert rejected["audit_valid"] is False
    assert "post_reset_source_writer_detected" in rejected["audit_failures"]


def test_report_only_layer_catalog_permits_only_session_report_delta():
    catalog = {
        "records": [
            {
                "path": path,
                "api_schemas": ["PhysxContactReportAPI"],
                "properties": [
                    {"name": "physxContactReport:threshold", "value": 0.0},
                    {
                        "name": "physxContactReport:reportPairs",
                        "targets": [],
                        "list_op": "explicit",
                    },
                ],
                "metadata": {},
            }
            for path in probe.REPORT_BODY_PATHS
        ]
    }
    catalog["sha256"] = probe._canonical_json_sha256(
        {"records": sorted(catalog["records"], key=lambda record: record["path"])}
    )
    assert probe.validate_report_only_layer_catalog(catalog)["audit_valid"] is True

    malformed = copy.deepcopy(catalog)
    malformed["records"][0]["properties"].append(
        {"name": "physics:mass", "value": 1.0}
    )
    rejected = probe.validate_report_only_layer_catalog(malformed)
    assert rejected["audit_valid"] is False
    assert "report_layer_unexpected_property" in rejected["audit_failures"]
    assert "report_layer_catalog_sha256_invalid" in rejected["audit_failures"]


def test_contact_lifecycle_identity_and_sidewall_topology_handle_rim_palm_and_unknown():
    accepted = probe.evaluate_contact_trace(
        [_first_contact_report()],
        identities=_identities(),
        geometry=_geometry(),
    )
    assert accepted["audit_valid"] is True
    assert accepted["samples"][0]["topology"]["qualified"] is True

    rim = probe.evaluate_contact_trace(
        [_first_contact_report(left_point=_point((-1.0, 0.0, 9.0), (1.0, 0.0, 0.0)))],
        identities=_identities(),
        geometry=_geometry(),
    )
    assert rim["audit_valid"] is True
    assert rim["samples"][0]["topology"]["qualified"] is False
    assert "outside_middle_sidewall" in rim["samples"][0]["topology"]["failure_reasons"]

    palm = probe.evaluate_contact_trace(
        [_first_contact_report(extra=HAND)],
        identities=_identities(),
        geometry=_geometry(),
    )
    assert palm["audit_valid"] is True
    assert palm["samples"][0]["forbidden_source_contact"] is True
    assert "SOURCE_OTHER" in palm["samples"][0]["classifications"]

    unknown_report = _first_contact_report()
    unknown_report["headers"][1]["collider1"] = "/World/unknown"
    unknown = probe.evaluate_contact_trace(
        [unknown_report], identities=_identities(), geometry=_geometry()
    )
    assert unknown["audit_valid"] is False
    assert "unresolved_contact_identity" in unknown["audit_failures"]


def test_unused_ambiguous_finger_geometry_does_not_block_precontact_observation():
    geometry = _geometry_with_ambiguous_unused_left_collider()
    identities = _identities_with_ambiguous_unused_left_collider()
    no_contact = probe.evaluate_sidewall_topology(
        {"pairs": []},
        geometry=geometry,
        identities=identities,
    )
    assert no_contact["audit_valid"] is True
    assert no_contact["qualified"] is False
    assert no_contact["failure_reasons"] == [
        "left_sidewall_contact_missing",
        "right_sidewall_contact_missing",
    ]

    bilateral = probe.ContactLifecycleAccumulator(_identities()).consume(
        physics_index=0,
        raw=_first_contact_report(),
    )
    accepted = probe.evaluate_sidewall_topology(
        bilateral,
        geometry=geometry,
        identities=identities,
    )
    assert accepted["audit_valid"] is True
    assert accepted["qualified"] is True

    ambiguous_active = copy.deepcopy(bilateral)
    for pair in ambiguous_active["pairs"]:
        if pair["classification"] == "LEFT_SOURCE":
            pair["pair"] = [SOURCE, LEFT_UNUSED]
    rejected = probe.evaluate_sidewall_topology(
        ambiguous_active,
        geometry=geometry,
        identities=identities,
    )
    assert rejected["audit_valid"] is False
    assert "topology_inward_face_ambiguous" in rejected["audit_failures"]


def test_v5_defers_unilateral_preclose_topology_but_rejects_weak_bilateral_alignment():
    right_only_report = {
        "headers": [
            _header("PERSIST", SOURCE, SUPPORT, contact_offset=0, contact_count=1),
            _header("PERSIST", SOURCE, RIGHT, contact_offset=1, contact_count=1),
        ],
        "contact_data": [
            _point((0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            _point((1.0, 0.0, 5.0), (-1.0, 0.0, 0.0)),
        ],
        "friction_anchors": [],
    }
    unilateral = probe.ContactLifecycleAccumulator(_identities()).consume(
        physics_index=0,
        raw=right_only_report,
    )
    deferred = probe.evaluate_sidewall_topology(
        unilateral,
        geometry=_geometry(),
        identities=_identities(),
        protocol=_v5_protocol(),
    )
    assert deferred["audit_valid"] is True
    assert deferred["qualified"] is False
    assert deferred["failure_reasons"] == ["left_sidewall_contact_missing"]

    geometry = _geometry()
    angle = math.radians(40.0)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    geometry["finger_colliders"][RIGHT]["world_from_local"] = [
        [cosine, -sine, 0.0, 0.0],
        [sine, cosine, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [1.5 - 1.5 * cosine, 1.5 * sine, 0.0, 1.0],
    ]
    bilateral = probe.ContactLifecycleAccumulator(_identities()).consume(
        physics_index=0,
        raw=_first_contact_report(),
    )
    rejected = probe.evaluate_sidewall_topology(
        bilateral,
        geometry=geometry,
        identities=_identities(),
        protocol=_v5_protocol(),
    )
    assert rejected["audit_valid"] is True
    assert rejected["qualified"] is False
    assert "finger_inward_face_alignment_below_threshold" in rejected["failure_reasons"]


def test_v6_topology_uses_world_metre_face_and_pad_distances():
    geometry = _geometry()
    geometry["finger_colliders"] = {
        LEFT: _bound((-200.0, -50.0, 100.0), (-100.0, 50.0, 900.0), matrix=[
            [0.01, 0.0, 0.0, 0.0],
            [0.0, 0.01, 0.0, 0.0],
            [0.0, 0.0, 0.01, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]),
        RIGHT: _bound((100.0, -50.0, 100.0), (200.0, 50.0, 900.0), matrix=[
            [0.01, 0.0, 0.0, 0.0],
            [0.0, 0.01, 0.0, 0.0],
            [0.0, 0.0, 0.01, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]),
    }

    def topology_for(left_position, right_position):
        report = _first_contact_report(
            left_point=_point(left_position, (1.0, 0.0, 0.0))
        )
        report["contact_data"][2] = _point(right_position, (-1.0, 0.0, 0.0))
        sample = probe.ContactLifecycleAccumulator(_identities()).consume(
            physics_index=0,
            raw=report,
        )
        return probe.evaluate_sidewall_topology(
            sample,
            geometry=geometry,
            identities=_identities(),
            protocol=_v6_protocol(),
        )

    accepted = topology_for((-0.997, 0.0, 5.0), (0.997, 0.0, 5.0))
    assert accepted["audit_valid"] is True
    assert accepted["qualified"] is True

    face_miss = topology_for((-0.994, 0.0, 5.0), (0.994, 0.0, 5.0))
    assert face_miss["audit_valid"] is True
    assert face_miss["qualified"] is False
    assert "finger_inward_face_missing" in face_miss["failure_reasons"]

    pad_edge = topology_for((-0.997, 0.4995, 5.0), (0.997, 0.4995, 5.0))
    assert pad_edge["audit_valid"] is True
    assert pad_edge["qualified"] is False
    assert "finger_pad_edge_contact" in pad_edge["failure_reasons"]

    outside_pad = topology_for((-0.997, 0.51, 5.0), (0.997, 0.51, 5.0))
    assert outside_pad["audit_valid"] is True
    assert outside_pad["qualified"] is False
    assert "finger_pad_edge_contact" in outside_pad["failure_reasons"]


def test_runtime_live_geometry_preserves_the_v6_face_distance_tolerance(monkeypatch):
    sealed = _geometry()

    def runtime_bound(_stage, path):
        if path == SOURCE:
            return sealed["source"]
        return sealed["finger_colliders"][path]

    monkeypatch.setattr(probe, "_runtime_bound", runtime_bound)

    live = probe._runtime_live_geometry(object(), sealed)

    assert live["inward_face_distance_tolerance_m"] == pytest.approx(0.005)


def test_v6_distinguishes_loaded_contacts_from_separated_contact_report_proximity():
    proximity = _first_contact_report(extra=HAND)
    proximity["contact_data"][-1]["separation"] = 0.01
    evaluated = probe.evaluate_contact_trace(
        [proximity],
        identities=_identities(
            support_colliders=[SUPPORT, TABLE_SUPPORT], other_colliders=[]
        ),
        geometry=_geometry(),
        protocol=_v6_protocol(),
    )
    assert evaluated["audit_valid"] is True, evaluated
    sample = evaluated["samples"][0]
    assert sample["forbidden_source_contact"] is False
    assert sample["physical_classifications"] == [
        "LEFT_SOURCE",
        "RIGHT_SOURCE",
        "SOURCE_SUPPORT",
    ]
    assert sample["noncontact_clearance_m"] == {"SOURCE_OTHER": 0.01}

    loaded = _first_contact_report(extra=HAND)
    sample = probe.evaluate_contact_trace(
        [loaded],
        identities=_identities(
            support_colliders=[SUPPORT, TABLE_SUPPORT], other_colliders=[]
        ),
        geometry=_geometry(),
        protocol=_v6_protocol(),
    )["samples"][0]
    assert sample["forbidden_source_contact"] is True
    assert "SOURCE_OTHER" in sample["physical_classifications"]


def test_first_contact_observation_preserves_persistent_pairs_without_crediting_them():
    headers = [
        _header("PERSIST", SOURCE, SUPPORT, contact_offset=0, contact_count=1),
        _header("PERSIST", SOURCE, LEFT, contact_offset=1, contact_count=1),
        _header("PERSIST", SOURCE, RIGHT, contact_offset=2, contact_count=1),
        _header("PERSIST", SOURCE, HAND, contact_offset=3, contact_count=1),
        _header("PERSIST", LEFT, SUPPORT, contact_offset=4, contact_count=1),
    ]
    report = {
        "headers": headers,
        "contact_data": [
            _point((0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            _point((-1.0, 0.0, 5.0), (1.0, 0.0, 0.0)),
            _point((1.0, 0.0, 5.0), (-1.0, 0.0, 0.0)),
            _point((0.0, 0.0, 5.0), (1.0, 0.0, 0.0)),
            _point((-2.0, 0.0, 5.0), (1.0, 0.0, 0.0)),
        ],
        "friction_anchors": [],
    }
    accumulator = probe.ContactLifecycleAccumulator(_identities())
    first = accumulator.consume(physics_index=0, raw=report)
    assert all(pair["bootstrap"] is True for pair in first["pairs"])
    assert {pair["classification"] for pair in first["pairs"]} == {
        "SOURCE_SUPPORT",
        "LEFT_SOURCE",
        "RIGHT_SOURCE",
        "SOURCE_OTHER",
        "ROBOT_ENVIRONMENT",
    }

    followup = accumulator.consume(physics_index=1, raw=report)
    assert all(pair["bootstrap"] is False for pair in followup["pairs"])

    late = probe.ContactLifecycleAccumulator(_identities())
    support_only = {
        "headers": [_header("PERSIST", SOURCE, SUPPORT, contact_offset=0, contact_count=1)],
        "contact_data": [_point((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))],
        "friction_anchors": [],
    }
    late.consume(physics_index=0, raw=support_only)
    with pytest.raises(probe.ContactAuditError, match="contact_lifecycle_invalid"):
        late.consume(
            physics_index=1,
            raw={
                "headers": [
                    _header("PERSIST", SOURCE, SUPPORT, contact_offset=0, contact_count=1),
                    _header("PERSIST", SOURCE, LEFT, contact_offset=1, contact_count=1),
                ],
                "contact_data": [
                    _point((0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
                    _point((-1.0, 0.0, 5.0), (1.0, 0.0, 0.0)),
                ],
                "friction_anchors": [],
            },
        )


def test_contact_lifecycle_retains_compact_recent_pair_history_for_failure_evidence():
    accumulator = probe.ContactLifecycleAccumulator(_identities())
    accumulator.consume(physics_index=0, raw=_first_contact_report())

    assert list(accumulator.recent_samples) == [
        {
            "physics_index": 0,
            "pairs": [
                {
                    "pair": sorted((SOURCE, SUPPORT)),
                    "classification": "SOURCE_SUPPORT",
                    "events": ["PERSIST"],
                    "current": True,
                    "transient": False,
                    "bootstrap": True,
                    "observer_activation": False,
                    "header_count": 1,
                    "contact_count": 1,
                    "friction_anchor_count": 0,
                },
                {
                    "pair": sorted((SOURCE, LEFT)),
                    "classification": "LEFT_SOURCE",
                    "events": ["FOUND"],
                    "current": True,
                    "transient": False,
                    "bootstrap": False,
                    "observer_activation": False,
                    "header_count": 1,
                    "contact_count": 1,
                    "friction_anchor_count": 0,
                },
                {
                    "pair": sorted((SOURCE, RIGHT)),
                    "classification": "RIGHT_SOURCE",
                    "events": ["FOUND"],
                    "current": True,
                    "transient": False,
                    "bootstrap": False,
                    "observer_activation": False,
                    "header_count": 1,
                    "contact_count": 1,
                    "friction_anchor_count": 0,
                },
            ],
            "support": {
                "present": True,
                "events": ["PERSIST"],
                "current": True,
                "header_count": 1,
                "contact_count": 1,
                "friction_anchor_count": 0,
                "lost_header_count": 0,
                "observer_activation": False,
            },
        }
    ]


def test_first_observation_non_support_contacts_cannot_pass_the_lift_trace():
    trace = _passing_trace()
    trace[0]["contact"]["classifications"] = [
        "SOURCE_SUPPORT",
        "LEFT_SOURCE",
        "RIGHT_SOURCE",
        "SOURCE_OTHER",
        "ROBOT_ENVIRONMENT",
    ]
    rejected = probe.evaluate_native_lift_pour_trace(
        trace,
        retention_steps=60,
        rise_threshold_m=0.12,
    )
    assert rejected["audit_valid"] is True
    assert rejected["physical_passed"] is False
    assert "first_observation_source_finger_contact" in rejected["physical_failures"]
    assert "first_observation_forbidden_source_contact" in rejected["physical_failures"]
    assert "first_observation_robot_environment_contact" in rejected["physical_failures"]


def test_parent_contact_replay_binds_raw_physics_index_to_transition_index():
    report = _first_contact_report()
    report.update(
        {
            "physics_index": 1,
            "immediate_read_index": 0,
            "immediate_read_count": 1,
        }
    )
    rejected = probe.evaluate_contact_trace(
        [report],
        identities=_identities(),
        geometry=_geometry(),
        require_immediate_read=True,
    )
    assert rejected["audit_valid"] is False
    assert "contact_immediate_read_contract_invalid" in rejected["audit_failures"]


def test_support_lost_state_machine_requires_explicit_awake_zero_data_lost_and_never_recontact():
    first = _first_contact_report()
    lost = {
        "headers": [
            _header("LOST", SOURCE, SUPPORT, contact_offset=0, contact_count=0),
            _header("LOST", SOURCE, LEFT, contact_offset=0, contact_count=0),
            _header("LOST", SOURCE, RIGHT, contact_offset=0, contact_count=0),
        ],
        "contact_data": [],
        "friction_anchors": [],
    }
    after = {"headers": [], "contact_data": [], "friction_anchors": []}
    parsed = probe.evaluate_contact_trace(
        [first, lost, after], identities=_identities(), geometry=_geometry()
    )
    lifecycle = probe.evaluate_support_lifecycle(
        parsed["samples"], [_state(0.0), _state(0.01), _state(0.02)]
    )
    assert lifecycle["audit_valid"] is True
    assert lifecycle["support_valid"] is True
    assert lifecycle["loss_index"] == 1
    assert lifecycle["states"] == ["CURRENT", "LOST", "LOST"]

    recontact = {
        "headers": [_header("FOUND", SOURCE, SUPPORT, contact_offset=0, contact_count=1)],
        "contact_data": [_point((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))],
        "friction_anchors": [],
    }
    parsed = probe.evaluate_contact_trace(
        [first, lost, recontact], identities=_identities(), geometry=_geometry()
    )
    lifecycle = probe.evaluate_support_lifecycle(
        parsed["samples"], [_state(0.0), _state(0.01), _state(0.02)]
    )
    assert lifecycle["audit_valid"] is True
    assert lifecycle["support_valid"] is False
    assert "support_recontact" in lifecycle["physical_failures"]

    missing = probe.evaluate_contact_trace(
        [{"headers": [], "contact_data": [], "friction_anchors": []}],
        identities=_identities(),
        geometry=_geometry(),
    )
    lifecycle = probe.evaluate_support_lifecycle(missing["samples"], [_state(0.0)])
    assert lifecycle["audit_valid"] is False
    assert "support_initial_state_unknown" in lifecycle["audit_failures"]


def test_topology_rejects_a_missing_pinned_pad_margin():
    geometry = _geometry()
    geometry.pop("pad_edge_margin_m")
    result = probe.evaluate_contact_trace(
        [_first_contact_report()],
        identities=_identities(),
        geometry=geometry,
    )
    assert result["audit_valid"] is False
    assert "contact_topology_authority_invalid" in result["audit_failures"]


def test_action_indexing_requires_exact_apply_and_event_two_joint_six_velocity():
    records = [
        _action_record(0, action={"joint_positions": [None] * 7 + [0.028, 0.028]}, pick_event=4),
        _action_record(1, action={"joint_positions": [0.0] * 9}, pick_event=5),
        _action_record(
            2,
            action={"joint_velocities": [None] * 6 + [-1.0] + [None, None]},
            pour_event=2,
            phase_before="POURING",
            phase_after="POURING",
        ),
    ]
    ledger = probe.evaluate_action_ledger(records, maximum_production_steps=1500)
    assert ledger["audit_valid"] is True
    assert ledger["close_action_index"] == 0
    assert ledger["lift_action_index"] == 1
    assert ledger["k_lift"] == 2
    assert ledger["pour_action_index"] == 2
    assert ledger["k_pour"] == 3

    duplicate = copy.deepcopy(records)
    duplicate[1]["apply_count"] = 2
    rejected = probe.evaluate_action_ledger(duplicate, maximum_production_steps=1500)
    assert rejected["audit_valid"] is False
    assert "action_apply_contract_invalid" in rejected["audit_failures"]

    zero_velocity = copy.deepcopy(records)
    zero_velocity[2] = _action_record(
        2,
        action={"joint_velocities": [None] * 6 + [0.0] + [None, None]},
        pour_event=2,
        phase_before="POURING",
        phase_after="POURING",
    )
    physical = probe.evaluate_action_ledger(zero_velocity, maximum_production_steps=1500)
    assert physical["audit_valid"] is True
    assert physical["native_sequence_valid"] is False
    assert "pour_event_two_nonzero_joint_six_velocity_missing" in physical["physical_failures"]


def test_action_ledger_uses_the_configured_retention_limit_for_continuations():
    records = [_action_record(index) for index in range(3)]
    result = probe.evaluate_action_ledger(
        records,
        maximum_production_steps=1,
        retention_steps=1,
    )
    assert result["audit_valid"] is False
    assert "action_ledger_records_invalid" in result["audit_failures"]


def test_lift_retention_and_post_event_two_rotation_have_clean_failure_boundary():
    accepted = probe.evaluate_native_lift_pour_trace(
        _passing_trace(), retention_steps=60, rise_threshold_m=0.12
    )
    assert accepted["audit_valid"] is True
    assert accepted["physical_passed"] is True
    assert accepted["k_lift"] == 11
    assert accepted["k_loss"] == 12
    assert accepted["k_rise"] == 13
    assert accepted["retention_count"] == 60
    assert accepted["rotation_degrees"] == pytest.approx(60.0)

    short = _passing_trace()[:-1]
    failed = probe.evaluate_native_lift_pour_trace(
        short, retention_steps=60, rise_threshold_m=0.12
    )
    assert failed["audit_valid"] is True
    assert failed["physical_passed"] is False
    assert "retention_window_incomplete" in failed["physical_failures"]

    no_rotation = _passing_trace()
    for record in no_rotation:
        record["post"]["orientation_wxyz"] = [1.0, 0.0, 0.0, 0.0]
    failed = probe.evaluate_native_lift_pour_trace(
        no_rotation, retention_steps=60, rise_threshold_m=0.12
    )
    assert failed["audit_valid"] is True
    assert failed["physical_passed"] is False
    assert "post_pour_rotation_threshold_not_reached" in failed["physical_failures"]

    malformed = _passing_trace()
    malformed[14]["contact"]["contact_read_once"] = False
    rejected = probe.evaluate_native_lift_pour_trace(
        malformed, retention_steps=60, rise_threshold_m=0.12
    )
    assert rejected["audit_valid"] is False
    assert "contact_authority_missing" in rejected["audit_failures"]


def test_parent_classifies_clean_failure_separately_from_audit_and_runtime_errors():
    clean_failure = probe.classify_parent_result(
        runtime_error=False,
        audit_no_go=False,
        physical_passed=False,
    )
    assert clean_failure == {
        "decision": "NATIVE_EXPERT_UNBOUND_LIFT_FAIL",
        "lifecycle_status": "completed",
        "clean_physical_failure": True,
    }

    audit = probe.classify_parent_result(
        runtime_error=False,
        audit_no_go=True,
        physical_passed=False,
    )
    assert audit["decision"] == "NATIVE_EXPERT_UNBOUND_AUDIT_NO_GO"
    assert audit["lifecycle_status"] == "completed"

    runtime = probe.classify_parent_result(
        runtime_error=True,
        audit_no_go=True,
        physical_passed=False,
    )
    assert runtime["decision"] == "PROBE_RUNTIME_ERROR"
    assert runtime["lifecycle_status"] == "failed"


def _fake_parent_child_result(treatment, transitions, *, source_physical_valid=True):
    report_layer = (
        None
        if treatment == "control"
        else {"catalog": {}, "post_catalog": {}}
    )
    evidence = {
        "source_physical_valid": source_physical_valid,
        "writer_audit": {},
        "runtime_identity_pre": {"sha256": "a" * 64},
        "report_layer": report_layer,
    }
    close_writer_audit = _writer_audit()
    close_writer_audit["writer_audit_snapshot_phase"] = "after_controller_close"
    return {
        "process_runtime_error": False,
        "provisional": {"runtime_status": "ok", "runtime_evidence": evidence},
        "trace": [
            {"kind": "transition", "payload": copy.deepcopy(transition)}
            for transition in transitions
        ],
        "cleanup": {
            "writer_audit": close_writer_audit,
            "writer_audit_snapshot_phase": "after_controller_close",
            "post_close_mutation_events": [],
        },
    }


def test_parent_fake_children_require_both_dynamic_source_contracts(monkeypatch):
    transitions = _passing_trace()
    child_results = {
        "control": _fake_parent_child_result(
            "control", transitions, source_physical_valid=False
        ),
        "instrumented": _fake_parent_child_result("instrumented", transitions),
    }

    monkeypatch.setattr(
        probe,
        "_evaluate_local_runtime_audits",
        lambda evidence, _transitions, *, diagnostic, close_mutation_events=(): {
            "audit_valid": True,
            "audit_failures": [],
            "evaluations": {
                "source_contract": {
                    "physical_valid": evidence["source_physical_valid"],
                }
            },
        },
    )
    monkeypatch.setattr(
        probe,
        "validate_report_only_layer_catalog",
        lambda _catalog: {"audit_valid": True, "audit_failures": []},
    )
    monkeypatch.setattr(
        probe,
        "_parent_recompute_instrumented_contacts",
        lambda _transitions, _evidence, **_kwargs: {
            "audit_valid": True,
            "audit_failures": [],
            "support_lifecycle": {"support_valid": True},
            "transitions": _passing_trace(),
        },
    )

    config = probe.freeze_diagnostic_config(
        CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )["config"]
    result = probe.recompute_parent_evidence(child_results, config=config)
    assert result["components"] == {
        "runtime_error": False,
        "audit_no_go": False,
        "physical_passed": False,
    }
    assert result["decision"] == "NATIVE_EXPERT_UNBOUND_LIFT_FAIL"


def test_parent_fake_children_classify_dual_cap_exhaustion_as_clean_failure(monkeypatch):
    exhausted = _passing_trace()
    exhausted[20]["production_terminal"] = False
    exhausted[20]["terminal_outcome"] = None
    exhausted[20]["terminal_success"] = None
    child_results = {
        treatment: _fake_parent_child_result(treatment, exhausted)
        for treatment in probe.TREATMENTS
    }

    monkeypatch.setattr(
        probe,
        "_evaluate_local_runtime_audits",
        lambda evidence, _transitions, *, diagnostic, close_mutation_events=(): {
            "audit_valid": True,
            "audit_failures": [],
            "evaluations": {"source_contract": {"physical_valid": True}},
        },
    )
    monkeypatch.setattr(
        probe,
        "validate_report_only_layer_catalog",
        lambda _catalog: {"audit_valid": True, "audit_failures": []},
    )
    monkeypatch.setattr(
        probe,
        "_parent_recompute_instrumented_contacts",
        lambda _transitions, _evidence, **_kwargs: {
            "audit_valid": True,
            "audit_failures": [],
            "support_lifecycle": {"support_valid": True},
            "transitions": copy.deepcopy(exhausted),
        },
    )

    config = probe.freeze_diagnostic_config(
        CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )["config"]
    result = probe.recompute_parent_evidence(child_results, config=config)
    assert result["components"] == {
        "runtime_error": False,
        "audit_no_go": False,
        "physical_passed": False,
    }
    assert result["decision"] == "NATIVE_EXPERT_UNBOUND_LIFT_FAIL"


def test_control_instrumented_comparison_rejects_report_layer_perturbation():
    control = _passing_trace()
    instrumented = copy.deepcopy(control)
    comparison = probe.evaluate_control_instrumented_nonperturbation(
        control, instrumented
    )
    assert comparison["audit_valid"] is True
    assert comparison["perturbation_detected"] is False

    instrumented[17]["post"]["origin_m"][0] = 0.0002
    comparison = probe.evaluate_control_instrumented_nonperturbation(
        control, instrumented
    )
    assert comparison["audit_valid"] is False
    assert "nonperturbation_origin_mismatch" in comparison["audit_failures"]


def test_runtime_version_identity_uses_distribution_metadata_or_kit_not_module_dunder(
    monkeypatch,
):
    class ModuleWithoutVersion:
        pass

    def metadata_version(distribution):
        if distribution == "isaacsim":
            return "4.1.0.0"
        raise probe.importlib_metadata.PackageNotFoundError

    monkeypatch.setattr(probe.importlib_metadata, "version", metadata_version)
    identity = probe._runtime_version_identity(ModuleWithoutVersion())
    assert identity["isaac_sim_version"] == "4.1.0.0"
    assert identity["version_sources"]["distribution:isaacsim"] == "4.1.0.0"

    monkeypatch.setattr(
        probe.importlib_metadata,
        "version",
        lambda _distribution: (_ for _ in ()).throw(
            probe.importlib_metadata.PackageNotFoundError
        ),
    )

    class KitApp:
        def get_app_version(self):
            return "4.1.0"

    fallback = probe._runtime_version_identity(ModuleWithoutVersion(), kit_app=KitApp())
    assert fallback["isaac_sim_version"] == "4.1.0.0"
    assert fallback["version_sources"]["kit_app"] == "4.1.0"


def test_read_only_source_adapter_uses_legacy_rigid_prim_view_without_xform_authoring():
    class RigidPrimView:
        instances = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.count = 1
            self.prim_paths = [SOURCE]
            self.read_calls = []
            type(self).instances.append(self)

        def initialize(self):
            self.read_calls.append("initialize")

        def get_world_poses(self):
            self.read_calls.append("world_poses")
            return [[0.1, 0.2, 0.3]], [[0.8660254, 0.0, 0.0, 0.5]]

        def get_linear_velocities(self):
            self.read_calls.append("linear_velocities")
            return [[1.0, 2.0, 3.0]]

        def get_angular_velocities(self):
            self.read_calls.append("angular_velocities")
            return [[4.0, 5.0, 6.0]]

    adapter = probe.RuntimeReadOnlySourceAdapter(RigidPrimView, SOURCE)
    adapter.initialize()

    view = RigidPrimView.instances[0]
    assert view.kwargs == {
        "prim_paths_expr": SOURCE,
        "name": "native_unbound_source_reader",
        "reset_xform_properties": False,
        "prepare_contact_sensors": False,
    }
    assert adapter.get_world_pose() == pytest.approx(
        ([0.1, 0.2, 0.3], [0.8660254, 0.0, 0.0, 0.5])
    )
    assert adapter.get_linear_velocity() == pytest.approx([1.0, 2.0, 3.0])
    assert adapter.get_angular_velocity() == pytest.approx([4.0, 5.0, 6.0])
    assert view.read_calls == [
        "initialize",
        "world_poses",
        "linear_velocities",
        "angular_velocities",
    ]
    assert adapter.contract()["read_only"] is True
    assert adapter.contract()["kind"] == "omni.isaac.core.prims.RigidPrimView"
    assert not any(name.startswith("set_") for name in vars(type(adapter)))


def test_static_property_snapshot_contract_excludes_live_xforms_and_velocities(monkeypatch):
    calls = []

    def static_properties(_stage, path, **kwargs):
        calls.append((path, kwargs))
        return {"path": path, "attributes": [], "relationships": [], "material_bindings": []}

    monkeypatch.setattr(probe, "_runtime_physics_properties", static_properties)
    snapshot = probe._runtime_source_robot_property_snapshot(
        object(),
        {
            "source_colliders": [SOURCE],
            "left_colliders": [LEFT],
            "right_colliders": [RIGHT],
            "hand_colliders": [HAND],
        },
    )

    assert set(snapshot) == {"source", "left_finger", "right_finger", "hand"}
    assert all(kwargs.get("include_xforms") is False for _path, kwargs in calls)
    assert probe._is_static_physics_attribute("physics:velocity") is False
    assert probe._is_static_physics_attribute("physics:angularVelocity") is False
    assert probe._is_static_physics_attribute("physxRigidBody:maxLinearVelocity") is True


def test_dynamic_source_contract_rejects_authored_center_of_mass_override():
    contract = _dynamic_source_contract()
    contract["body_origin_metric"] = {
        "metric": "rigid_body_origin",
        "authored_center_of_mass_overrides": ["/World/beaker2/mesh:physxRigidBody:centerOfMass"],
        "valid": False,
    }

    result = probe.evaluate_dynamic_source_contract(contract)
    assert result["audit_valid"] is False
    assert "source_center_of_mass_authority_invalid" in result["audit_failures"]


def test_coupling_audit_rejects_external_semantic_relation_mutations_and_unknown_groups():
    transient = probe.evaluate_coupling_inventory(
        {
            "relations": [],
            "mutation_events": [
                {
                    "path": "/World/externalCollisionGroup.collection:includes",
                    "kind": "info",
                    "fields": ["targetPaths"],
                }
            ],
        }
    )
    assert transient["audit_valid"] is False
    assert "external_relation_mutation_detected" in transient["audit_failures"]

    unresolved = probe.evaluate_coupling_inventory(
        {
            "relations": [
                {
                    "kind": "collection",
                    "endpoints": ["/World/externalCollisionGroup"],
                    "identity_valid": False,
                }
            ]
        }
    )
    assert unresolved["audit_valid"] is False
    assert "unsupported_relation_endpoint" in unresolved["audit_failures"]


def test_relation_mutation_detector_does_not_treat_body_group_path_names_as_semantic():
    assert probe._is_semantic_relation_mutation(
        {
            "path": "/World/DryingBox_01/body/Group/door/mesh.physics:velocity",
            "kind": "info",
            "fields": ["default"],
        }
    ) is False
    assert probe._is_semantic_relation_mutation(
        {
            "path": "/World/externalCollisionGroup.collection:includes",
            "kind": "info",
            "fields": ["targetPaths"],
        }
    ) is True
    assert probe._is_semantic_relation_mutation(
        {
            "path": "/World/external",
            "kind": "resync",
            "fields": [],
        }
    ) is True


def test_static_source_robot_audit_compares_pre_reset_and_allows_only_root_placement():
    before_reset = _property_snapshot("before")
    after_reset = _property_snapshot("before")
    accepted = probe.evaluate_source_robot_property_mutations(
        before_reset,
        [after_reset],
        [],
        pre_reset_mutation_events=[
            {
                "path": SOURCE_ROOT,
                "kind": "info",
                "fields": ["xformOp:translate", "xformOpOrder"],
            }
        ],
    )
    assert accepted["audit_valid"] is True

    changed = _property_snapshot("before")
    changed["source"]["mass"] = 0.03
    rejected = probe.evaluate_source_robot_property_mutations(
        before_reset,
        [changed],
        [],
        pre_reset_mutation_events=[],
    )
    assert rejected["audit_valid"] is False
    assert "source_robot_physical_properties_changed" in rejected["audit_failures"]

    raw_change = probe.evaluate_source_robot_property_mutations(
        before_reset,
        [after_reset],
        [],
        pre_reset_mutation_events=[
            {
                "path": SOURCE,
                "kind": "info",
                "fields": ["physics:mass"],
            }
        ],
    )
    assert raw_change["audit_valid"] is False
    assert "pre_reset_source_robot_mutation_notice" in raw_change["audit_failures"]

    property_path_change = probe.evaluate_source_robot_property_mutations(
        before_reset,
        [after_reset],
        [],
        pre_reset_mutation_events=[
            {
                "path": SOURCE + ".physics:mass",
                "kind": "info",
                "fields": ["default"],
            }
        ],
    )
    assert property_path_change["audit_valid"] is False
    assert "pre_reset_source_robot_mutation_notice" in property_path_change["audit_failures"]


def test_source_robot_snapshot_ignores_only_report_api_metadata_on_report_bodies():
    before_reset = _property_snapshot("before")
    before_reset["hand"] = {
        "applied_schemas": [
            {"path": HAND_BODY, "schemas": ["PhysicsRigidBodyAPI"]}
        ],
        "attributes": [],
        "relationships": [],
        "sha256": "before",
    }
    report_setup = copy.deepcopy(before_reset)
    report_setup["hand"]["applied_schemas"][0]["schemas"].append(
        "PhysxContactReportAPI"
    )
    report_setup["hand"]["attributes"] = [
        {
            "path": HAND_BODY,
            "name": "physxContactReport:threshold",
            "value": 0.0,
        }
    ]
    report_setup["hand"]["relationships"] = [
        {
            "path": HAND_BODY,
            "name": "physxContactReport:reportPairs",
            "targets": [],
        }
    ]
    report_setup["hand"]["sha256"] = "after"
    accepted = probe.evaluate_source_robot_property_mutations(
        before_reset,
        [report_setup],
        [],
    )
    assert accepted["audit_valid"] is True

    changed = copy.deepcopy(report_setup)
    changed["hand"]["attributes"].append(
        {"path": HAND_BODY, "name": "physics:mass", "value": 0.03}
    )
    rejected = probe.evaluate_source_robot_property_mutations(
        before_reset,
        [changed],
        [],
    )
    assert rejected["audit_valid"] is False
    assert "source_robot_physical_properties_changed" in rejected["audit_failures"]


def test_cube_audit_requires_recursive_descendant_state():
    incomplete = _cube_snapshot()
    incomplete.pop("descendant_physics_state")
    result = probe.evaluate_cube_immutability(incomplete, [incomplete], [])
    assert result["audit_valid"] is False
    assert "cube_baseline_snapshot_invalid" in result["audit_failures"]


def test_cube_audit_rejects_descendant_property_path_notice():
    snapshot = _cube_snapshot()
    result = probe.evaluate_cube_immutability(
        snapshot,
        [copy.deepcopy(snapshot)],
        [{"path": SUPPORT + ".physics:mass", "kind": "info", "fields": ["default"]}],
    )
    assert result["audit_valid"] is False
    assert "cube_mutation_notice" in result["audit_failures"]


def test_writer_audit_requires_local_plural_and_explicit_force_impulse_surfaces():
    audit = _writer_audit()
    for surface in (
        "source_adapter_read_only",
        "plural_prim_view_local_poses",
        "plural_prim_view_linear_velocities",
        "plural_prim_view_angular_velocities",
        "physics_view_forces",
        "physics_view_torques",
        "physics_view_impulses",
        "physics_view_kinematic_targets",
        "physics_view_dynamic_targets",
    ):
        assert surface in probe.REQUIRED_WRITER_AUDIT_SURFACES
        audit["coverage"][surface] = False

    result = probe.evaluate_writer_target_force_gripper_audit(audit)
    assert result["audit_valid"] is False
    assert "writer_audit_coverage_incomplete" in result["audit_failures"]


def test_writer_audit_marks_mutation_notice_covered_only_after_activation():
    audit = probe._RuntimeWriteAudit()
    assert audit.report(mutation_notice_active=False)["coverage"]["usd_mutation_notice"] is False

    audit.activate_mutation_notice()
    assert audit.report(mutation_notice_active=True)["coverage"]["usd_mutation_notice"] is True


def test_nonperturbation_compares_terminal_awake_controller_and_action_receipts():
    control = _passing_trace()
    instrumented = copy.deepcopy(control)
    instrumented[20]["production_terminal"] = False
    instrumented[20]["terminal_outcome"] = None
    instrumented[20]["terminal_success"] = None
    instrumented[17]["post"]["awake"] = False
    instrumented[14]["controller_call_count"] = 0
    instrumented[14]["action_receipt"]["action_sha256"] = "0" * 64

    result = probe.evaluate_control_instrumented_nonperturbation(control, instrumented)
    assert result["audit_valid"] is False
    assert "nonperturbation_terminal_mismatch" in result["audit_failures"]
    assert "nonperturbation_awake_mismatch" in result["audit_failures"]
    assert "nonperturbation_controller_mismatch" in result["audit_failures"]
    assert "nonperturbation_action_receipt_mismatch" in result["audit_failures"]


def test_cap_exhaustion_is_a_clean_physical_failure_not_a_pass():
    exhausted = _passing_trace()
    exhausted[20]["production_terminal"] = False
    exhausted[20]["terminal_outcome"] = None
    exhausted[20]["terminal_success"] = None

    result = probe.evaluate_native_lift_pour_trace(
        exhausted,
        retention_steps=60,
        rise_threshold_m=0.12,
    )
    assert result["audit_valid"] is True
    assert result["physical_passed"] is False
    assert "normal_production_terminal_missing" in result["physical_failures"]


def test_unsuccessful_finished_terminal_is_not_a_normal_production_terminal():
    unsuccessful = _passing_trace()
    unsuccessful[20]["terminal_success"] = False

    result = probe.evaluate_native_lift_pour_trace(
        unsuccessful,
        retention_steps=60,
        rise_threshold_m=0.12,
    )
    assert result["audit_valid"] is True
    assert result["physical_passed"] is False
    assert "normal_production_terminal_missing" in result["physical_failures"]


def test_pour_gate_retains_height_and_contact_cleanliness_from_integration_to_rotation():
    below_threshold = _passing_trace()
    below_threshold[15]["post"]["origin_m"][2] = 0.01
    result = probe.evaluate_native_lift_pour_trace(
        below_threshold,
        retention_steps=60,
        rise_threshold_m=0.12,
    )
    assert result["physical_passed"] is False
    assert "pour_rotation_height_retention_lost" in result["physical_failures"]

    forbidden = _passing_trace()
    forbidden[15]["contact"]["forbidden_source_contact"] = True
    result = probe.evaluate_native_lift_pour_trace(
        forbidden,
        retention_steps=60,
        rise_threshold_m=0.12,
    )
    assert result["physical_passed"] is False
    assert "pour_rotation_forbidden_source_contact" in result["physical_failures"]


@pytest.mark.parametrize(
    "path, value",
    [
        (("diagnostic", "child_timeout_seconds"), 360),
        (("diagnostic", "stable_supported_steps"), 9),
        (("diagnostic", "stable_linear_speed_m_s"), 0.002),
        (("diagnostic", "stable_angular_speed_degrees_s"), 0.2),
        (("diagnostic", "stable_origin_displacement_m"), 0.0002),
        (("diagnostic", "post_pour_rotation_degrees"), 49.0),
        (("diagnostic", "topology", "normalized_height_range"), [0.1, 0.9]),
        (("diagnostic", "topology", "maximum_vertical_normal_cosine"), 0.3),
        (("diagnostic", "comparison_tolerances", "origin_m"), 0.001),
        (("diagnostic", "video", "sample_every_transitions"), 3),
    ],
)
def test_every_diagnostic_control_is_pinned(path, value, tmp_path):
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    target = config
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    altered = tmp_path / "altered.yaml"
    altered.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(ValueError, match="native_unbound_pinned_contract_mismatch"):
        probe.freeze_diagnostic_config(
            altered,
            production_config_path=PRODUCTION_CONFIG_PATH,
        )


def _write_fake_child_artifacts(
    directory,
    *,
    runtime_status="ok",
    lifecycle_status=None,
    terminal_payload=None,
):
    directory.mkdir()
    treatment = "control"
    run_nonce = "nonce"
    parent_pid = 123
    child_pid = 456
    run_id = "run-id"
    frozen = directory / probe.FROZEN_CONFIG_BASENAME
    frozen.write_bytes(b"{}\n")
    config_sha256 = probe.sha256_file(frozen)
    expected_lifecycle = {
        "ok": "measurement_complete_pending_application_close",
        "audit_no_go": "audit_no_go_pending_application_close",
        "runtime_error": "runtime_error_pending_application_close",
    }[runtime_status]
    lifecycle_status = lifecycle_status or expected_lifecycle
    terminal_payload = terminal_payload or {
        "runtime_status": runtime_status,
        "lifecycle_status": lifecycle_status,
    }
    trace = []
    trace.append(
        probe.make_trace_record(
            trace,
            treatment=treatment,
            run_nonce=run_nonce,
            parent_pid=parent_pid,
            child_pid=child_pid,
            run_id=run_id,
            kind="bootstrap",
            payload={"runtime_evidence": {}},
        )
    )
    trace.append(
        probe.make_trace_record(
            trace,
            treatment=treatment,
            run_nonce=run_nonce,
            parent_pid=parent_pid,
            child_pid=child_pid,
            run_id=run_id,
            kind="terminal",
            payload=terminal_payload,
        )
    )
    trace_path = directory / probe.TRACE_BASENAME
    probe.atomic_create_jsonl(trace_path, trace)
    cleanup = {
        "schema_version": 1,
        "manifest_type": "native_expert_empty_beaker_unbound_lift_cleanup_v1",
        "treatment": treatment,
        "run_nonce": run_nonce,
        "parent_pid": parent_pid,
        "child_pid": child_pid,
        "run_id": run_id,
        "trace_chain_sha256": trace[-1]["record_sha256"],
        "controller_closed": True,
        "collector_closed": True,
        "world_counter_before_controller_close": 10,
        "world_counter_after_controller_close": 10,
        "writer_audit_snapshot_phase": "after_controller_close",
        "writer_audit": {},
        "post_close_mutation_events": [],
        "runtime_status": runtime_status,
        "lifecycle_status": lifecycle_status,
    }
    probe.atomic_create_json(directory / probe.CLEANUP_BASENAME, cleanup)
    provisional = {
        "schema_version": 1,
        "manifest_type": probe.CHILD_MANIFEST_TYPE,
        "lifecycle_status": lifecycle_status,
        "runtime_status": runtime_status,
        "treatment": treatment,
        "run_nonce": run_nonce,
        "parent_pid": parent_pid,
        "child_pid": child_pid,
        "run_id": run_id,
        "config_sha256": config_sha256,
        "runtime_evidence": {},
        "trace_chain_sha256": trace[-1]["record_sha256"],
        "artifacts": {
            "frozen_config": probe._artifact_record(frozen, relative_to=directory),
            "trace": probe._artifact_record(trace_path, relative_to=directory),
        },
    }
    probe.atomic_create_json(directory / probe.PROVISIONAL_REPORT_BASENAME, provisional)
    return {
        "treatment": treatment,
        "run_nonce": run_nonce,
        "parent_pid": parent_pid,
        "child_pid": child_pid,
        "config_sha256": config_sha256,
    }


@pytest.mark.parametrize(
    "lifecycle_status, terminal_payload",
    [
        ("audit_no_go_pending_application_close", None),
        (
            None,
            {
                "runtime_status": "audit_no_go",
                "lifecycle_status": "audit_no_go_pending_application_close",
            },
        ),
    ],
)
def test_parent_rejects_fake_child_runtime_lifecycle_terminal_contradictions(
    tmp_path, lifecycle_status, terminal_payload
):
    identity = _write_fake_child_artifacts(
        tmp_path / "child",
        lifecycle_status=lifecycle_status,
        terminal_payload=terminal_payload,
    )

    with pytest.raises(ValueError, match="native_unbound_child_status_contradiction"):
        probe._validate_child_artifacts(
            treatment_dir=tmp_path / "child",
            **identity,
        )


def test_parent_cleanup_terminates_exited_fake_child_descendants(monkeypatch):
    class ExitedProcess:
        pid = 9876

        def poll(self):
            return 0

    calls = []
    monkeypatch.setattr(
        probe,
        "terminate_process_group",
        lambda process: calls.append(("terminate", process.pid)) or "POSTEXIT_SIGTERM",
    )
    monkeypatch.setattr(
        probe,
        "validate_process_quiescence",
        lambda process, *, collector_closed: calls.append(
            ("quiescence", process.pid, collector_closed)
        )
        or {"quiescent": True},
    )

    result = probe.cleanup_process_group_after_validation_error(ExitedProcess())
    assert result == {"termination": "POSTEXIT_SIGTERM", "quiescent": True}
    assert calls == [("terminate", 9876), ("quiescence", 9876, None)]


def test_termination_kills_surviving_descendants_after_live_child_exits(monkeypatch):
    class Process:
        pid = 9877
        returncode = 0

        def __init__(self):
            self.wait_calls = []

        def poll(self):
            return None if not self.wait_calls else 0

        def wait(self, *, timeout):
            self.wait_calls.append(timeout)
            return 0

    process = Process()
    signals = []
    members = iter(([7654], [], []))
    monkeypatch.setattr(probe.os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    monkeypatch.setattr(probe, "_process_group_members", lambda _pid: next(members))

    result = probe.terminate_process_group(
        process,
        term_grace_seconds=0.0,
        kill_grace_seconds=0.0,
    )
    assert result == "SIGTERM_POSTEXIT_SIGKILL"
    assert signals == [(9877, probe.signal.SIGTERM), (9877, probe.signal.SIGKILL)]


def test_parent_rejects_altered_video_bytes_against_fake_child_manifest(tmp_path):
    video = tmp_path / probe.VIDEO_BASENAME
    video.write_bytes(b"original video")
    frame_map = tmp_path / probe.VIDEO_MAP_BASENAME
    frame_map_payload = {
        "schema_version": 1,
        "treatment": "instrumented",
        "run_nonce": "nonce",
        "parent_pid": 123,
        "child_pid": 456,
        "run_id": "run-id",
        "frames": [
            {"video_frame_index": 0, "transition_index": 0, "world_index": 1}
        ],
    }
    probe.atomic_create_json(frame_map, frame_map_payload)
    video_artifact = probe._artifact_record(video, relative_to=tmp_path)
    map_artifact = probe._artifact_record(frame_map, relative_to=tmp_path)
    provisional = {
        "treatment": "instrumented",
        "run_nonce": "nonce",
        "parent_pid": 123,
        "child_pid": 456,
        "run_id": "run-id",
        "runtime_evidence": {
            "video_sample_every_transitions": 2,
            "video_artifacts": {
                "video": video_artifact,
                "frame_map": map_artifact,
                "frame_count": 1,
            }
        },
        "artifacts": {"video": video_artifact, "video_frame_map": map_artifact},
    }
    video.write_bytes(b"altered video")

    with pytest.raises(ValueError, match="native_unbound_video_artifact_manifest_invalid"):
        probe._validate_video_artifacts(tmp_path, provisional)


def test_static_closure_and_runtime_writer_audit_marks_absent_surfaces_not_applicable():
    class RigidPrimView:
        count = 1
        prim_paths = [SOURCE]

        def __init__(self, **_kwargs):
            pass

        def initialize(self):
            return None

        def get_world_poses(self):
            return [[0.0, 0.0, 0.0]], [[1.0, 0.0, 0.0, 0.0]]

        def get_linear_velocities(self):
            return [[0.0, 0.0, 0.0]]

        def get_angular_velocities(self):
            return [[0.0, 0.0, 0.0]]

    class ObjectUtils:
        def set_object_position(self, object_path, *_args, **_kwargs):
            return object_path

    class Gripper:
        grasped_object_path = None

        def add_object_to_gripper(self, object_path, *_args, **_kwargs):
            self.grasped_object_path = object_path

        def update_grasped_object_position(self):
            return None

        def release_object(self):
            self.grasped_object_path = None

    class Controller:
        gripper_control = Gripper()

    closure = probe._static_production_closure_audit(probe.PINNED_DIAGNOSTIC)
    assert closure["audit_valid"] is True
    assert "object_utils_set_object_position" in closure["required_runtime_surfaces"]
    assert "physics_view_forces" in closure["not_applicable_runtime_surfaces"]

    audit = probe._RuntimeWriteAudit()
    adapter = probe.RuntimeReadOnlySourceAdapter(RigidPrimView, SOURCE)
    adapter.initialize()
    object_utils = ObjectUtils()
    probe._install_runtime_write_audit(
        audit,
        source_adapter=adapter,
        controller=Controller(),
        object_utils=object_utils,
        static_production_closure=closure,
    )
    object_utils.set_object_position(SOURCE_ROOT, [0.0, 0.0, 0.0])
    audit.activate_mutation_notice()
    audit.open_epoch()
    report = audit.report(mutation_notice_active=True)

    assert report["surfaces"]["physics_view_forces"]["status"] == "not_applicable"
    assert report["surfaces"]["physics_view_forces"]["reachable"] is False
    assert probe.evaluate_writer_target_force_gripper_audit(report)["audit_valid"] is True


def test_mutation_ledger_allows_only_known_dynamic_world_writeback():
    known_dynamic_bodies = [SOURCE, LEFT_BODY, RIGHT_BODY, HAND_BODY]
    accepted = probe.evaluate_runtime_mutation_ledger(
        [
            {
                "phase": "world_step",
                "events": [
                    {
                        "path": SOURCE + ".xformOp:translate",
                        "kind": "info",
                        "fields": ["default"],
                    },
                    {
                        "path": LEFT_BODY,
                        "kind": "info",
                        "fields": ["physics:velocity"],
                    },
                ],
            }
        ],
        known_dynamic_body_paths=known_dynamic_bodies,
    )
    assert accepted["audit_valid"] is True
    assert accepted["forbidden_event_count"] == 0

    task_write = probe.evaluate_runtime_mutation_ledger(
        [
            {
                "phase": "task",
                "events": [
                    {
                        "path": SOURCE + ".xformOp:translate",
                        "kind": "info",
                        "fields": ["default"],
                    }
                ],
            }
        ],
        known_dynamic_body_paths=known_dynamic_bodies,
    )
    assert task_write["audit_valid"] is False
    assert "source_robot_mutation_outside_world_step" in task_write["audit_failures"]

    external_relation = probe.evaluate_runtime_mutation_ledger(
        [
            {
                "phase": "world_step",
                "events": [
                    {
                        "path": "/World/externalGroup.collection:includes",
                        "kind": "info",
                        "fields": ["targetPaths"],
                    }
                ],
            }
        ],
        known_dynamic_body_paths=known_dynamic_bodies,
    )
    assert external_relation["audit_valid"] is False
    assert "external_relation_mutation_detected" in external_relation["audit_failures"]


def test_mutation_ledger_records_pre_reset_setup_without_treating_it_as_execution_mutation():
    result = probe.evaluate_runtime_mutation_ledger(
        [
            {
                "phase": "pre_reset",
                "events": [
                    {"path": "/World/Camera1", "kind": "resync", "fields": []},
                    {
                        "path": SOURCE_ROOT + ".xformOp:translate",
                        "kind": "resync",
                        "fields": [],
                    },
                    {
                        "path": HAND_BODY,
                        "kind": "info",
                        "fields": ["apiSchemas"],
                    },
                    {
                        "path": LEFT_BODY + ".physics:velocity",
                        "kind": "info",
                        "fields": ["default"],
                    },
                    {"path": RIGHT_BODY, "kind": "info", "fields": []},
                    {
                        "path": "/World/ResetTransient.collection:includes",
                        "kind": "resync",
                        "fields": [],
                    },
                ],
            }
        ],
        known_dynamic_body_paths=[SOURCE, LEFT_BODY, RIGHT_BODY, HAND_BODY],
    )
    assert result["audit_valid"] is True
    assert result["forbidden_event_count"] == 0


def test_comparable_runtime_identity_ignores_only_ephemeral_local_franka_composition_hash():
    base = {
        "sha256": "a" * 64,
        "report_layer_catalog_sha256": "b" * 64,
        "local_franka_sha256": "c" * 64,
        "local_franka_root_sha256": "d" * 64,
        "local_franka_dependency_closure_sha256": "e" * 64,
    }
    other_layer = copy.deepcopy(base)
    other_layer["local_franka_sha256"] = "f" * 64
    assert probe._comparable_runtime_identity(base) == probe._comparable_runtime_identity(
        other_layer
    )

    different_root = copy.deepcopy(other_layer)
    different_root["local_franka_root_sha256"] = "0" * 64
    assert probe._comparable_runtime_identity(base) != probe._comparable_runtime_identity(
        different_root
    )


def test_relation_inventory_rejects_external_cross_root_and_source_force_schema():
    cross_root = probe.evaluate_coupling_inventory(
        {
            "relations": [
                {
                    "kind": "collision_group",
                    "owner_path": "/World/externalGroup",
                    "relationship": "collection:includes",
                    "endpoints": ["/World/externalGroup", SOURCE, "/World/external"],
                    "identity_valid": True,
                }
            ],
            "applied_schemas": [
                {
                    "path": "/World/externalGroup",
                    "schemas": ["UsdPhysics.CollisionGroup"],
                }
            ],
        }
    )
    assert cross_root["audit_valid"] is False
    assert "unknown_cross_root_collision_treatment" in cross_root["audit_failures"]

    force_schema = probe.evaluate_coupling_inventory(
        {
            "relations": [],
            "applied_schemas": [
                {
                    "path": SOURCE,
                    "schemas": ["PhysxSchema.PhysxForceFieldAPI"],
                }
            ],
        }
    )
    assert force_schema["audit_valid"] is False
    assert "source_relevant_applied_schema" in force_schema["audit_failures"]


def test_action_ledger_rejects_continuation_actions_and_event_two_outside_pouring():
    terminal = _action_record(0)
    terminal["production_terminal"] = True
    terminal["terminal_outcome"] = "FINISHED"
    terminal["terminal_success"] = True
    continuation = _action_record(
        1,
        action={"joint_positions": [0.0] * 9},
        phase_before="FINISHED",
        phase_after="FINISHED",
        state_present=False,
        continuation_index=0,
    )
    continuation_result = probe.evaluate_action_ledger(
        [terminal, continuation], maximum_production_steps=1500
    )
    assert continuation_result["audit_valid"] is False
    assert "continuation_action_forbidden" in continuation_result["audit_failures"]

    event_two = _action_record(
        0,
        action={"joint_velocities": [None] * 6 + [-1.0] + [None, None]},
        pour_event=2,
        phase_before="PICKING",
        phase_after="POURING",
    )
    event_two_result = probe.evaluate_action_ledger(
        [event_two], maximum_production_steps=1500
    )
    assert event_two_result["audit_valid"] is False
    assert "pour_event_two_phase_invalid" in event_two_result["audit_failures"]


def test_dynamic_source_requires_sealed_cooked_local_com_authority():
    missing = _dynamic_source_contract()
    missing.pop("source_local_com_authority")

    result = probe.evaluate_dynamic_source_contract(missing)
    assert result["audit_valid"] is False
    assert "source_local_com_authority_missing" in result["audit_failures"]


def test_cube_static_contract_requires_all_descendants_to_remain_static_and_nonmoving():
    baseline = _cube_snapshot()
    missing = copy.deepcopy(baseline)
    missing.pop("support_contract")

    result = probe.evaluate_cube_immutability(missing, [missing], [])
    assert result["audit_valid"] is False
    assert "cube_baseline_snapshot_invalid" in result["audit_failures"]

    moving = copy.deepcopy(baseline)
    moving["support_contract"]["nonmoving"] = False
    result = probe.evaluate_cube_immutability(baseline, [moving], [])
    assert result["audit_valid"] is False
    assert "cube_support_contract_invalid" in result["audit_failures"]


def test_pour_rotation_rejects_robot_environment_contact_before_acceptance():
    trace = _passing_trace()
    trace[15]["contact"]["robot_environment_contact"] = True

    result = probe.evaluate_native_lift_pour_trace(
        trace, retention_steps=60, rise_threshold_m=0.12
    )
    assert result["physical_passed"] is False
    assert "pour_rotation_robot_environment_contact" in result["physical_failures"]


def test_trace_validation_rejects_error_record_in_ok_lifecycle():
    records = []
    identity = {
        "treatment": "control",
        "run_nonce": "nonce",
        "parent_pid": 123,
        "child_pid": 456,
        "run_id": "run-id",
    }
    records.append(
        probe.make_trace_record(
            records, kind="bootstrap", payload={"runtime_evidence": {}}, **identity
        )
    )
    records.append(
        probe.make_trace_record(
            records,
            kind="audit_no_go",
            payload={"code": "unexpected", "detail": "unexpected", "evidence": None},
            **identity,
        )
    )
    records.append(
        probe.make_trace_record(
            records,
            kind="terminal",
            payload={
                "runtime_status": "ok",
                "lifecycle_status": "measurement_complete_pending_application_close",
            },
            **identity,
        )
    )

    with pytest.raises(ValueError, match="native_unbound_trace_status_contradiction"):
        probe.validate_trace_records(
            records,
            expected_treatment="control",
            expected_nonce="nonce",
            expected_parent_pid=123,
            expected_child_pid=456,
            expected_run_id="run-id",
            expected_runtime_status="ok",
            expected_lifecycle_status="measurement_complete_pending_application_close",
        )


def test_video_map_is_bound_to_actual_trace_transition_and_world_ids(tmp_path):
    video = tmp_path / probe.VIDEO_BASENAME
    video.write_bytes(b"video bytes")
    frame_map = tmp_path / probe.VIDEO_MAP_BASENAME
    probe.atomic_create_json(
        frame_map,
        {
            "schema_version": 1,
            "treatment": "instrumented",
            "run_nonce": "nonce",
            "parent_pid": 123,
            "child_pid": 456,
            "run_id": "run-id",
            "frames": [
                {"video_frame_index": 0, "transition_index": 0, "world_index": 99}
            ],
        },
    )
    video_artifact = probe._artifact_record(video, relative_to=tmp_path)
    map_artifact = probe._artifact_record(frame_map, relative_to=tmp_path)
    provisional = {
        "treatment": "instrumented",
        "run_nonce": "nonce",
        "parent_pid": 123,
        "child_pid": 456,
        "run_id": "run-id",
        "runtime_evidence": {
            "video_sample_every_transitions": 2,
            "video_artifacts": {
                "video": video_artifact,
                "frame_map": map_artifact,
                "frame_count": 1,
            },
        },
        "artifacts": {"video": video_artifact, "video_frame_map": map_artifact},
    }
    trace = [
        {
            "kind": "transition",
            "payload": {"transition_index": 0, "world_index": 100, "state_present": True},
        }
    ]

    with pytest.raises(ValueError, match="native_unbound_video_map_trace_mismatch"):
        probe._validate_video_artifacts(tmp_path, provisional, trace_records=trace)


def test_parent_cleans_descendants_and_confirms_quiescence_before_blocking_next_treatment(
    monkeypatch, tmp_path
):
    launched = []
    calls = []

    class ExitedProcess:
        returncode = 0

        def __init__(self, *_args, **_kwargs):
            self.pid = 8100 + len(launched)
            launched.append(self.pid)

        def poll(self):
            return 0

        def wait(self, *, timeout):
            assert timeout == 900.0
            return 0

    monkeypatch.setattr(probe, "build_parent_identity", lambda _config: {"identity": 1})
    monkeypatch.setattr(probe, "build_child_command", lambda **_kwargs: ["fake-child"])
    monkeypatch.setattr(probe.subprocess, "Popen", ExitedProcess)
    monkeypatch.setattr(
        probe,
        "validate_process_quiescence",
        lambda process, *, collector_closed: calls.append(
            ("quiescence", process.pid, collector_closed)
        )
        or (_ for _ in ()).throw(RuntimeError("descendant_still_alive")),
    )
    monkeypatch.setattr(
        probe,
        "cleanup_process_group_after_validation_error",
        lambda process: calls.append(("cleanup", process.pid))
        or {"termination": "SIGTERM", "quiescent": True},
    )
    monkeypatch.setattr(
        probe,
        "recompute_parent_evidence",
        lambda _children, *, config, **_kwargs: {
            "components": {
                "runtime_error": True,
                "audit_no_go": False,
                "physical_passed": False,
            },
            "decision": "PROBE_RUNTIME_ERROR",
            "evaluations": {},
        },
    )

    args = SimpleNamespace(
        config=CONFIG_PATH,
        out_dir=tmp_path / "probe-output",
        timeout_seconds=None,
    )
    assert probe._run_parent(args) == 2
    assert launched == [8100]
    assert calls == [("quiescence", 8100, None), ("cleanup", 8100)]


def test_continuation_semantic_events_and_dynamic_support_cannot_hide_after_terminal():
    terminal = _action_record(0)
    terminal["production_terminal"] = True
    terminal["terminal_outcome"] = "FINISHED"
    terminal["terminal_success"] = True
    continuation = _action_record(
        1,
        phase_before="FINISHED",
        phase_after="FINISHED",
        state_present=False,
        continuation_index=0,
        pick_event=4,
    )
    continuation_result = probe.evaluate_action_ledger(
        [terminal, continuation], maximum_production_steps=1500
    )
    assert continuation_result["audit_valid"] is False
    assert "continuation_action_forbidden" in continuation_result["audit_failures"]

    baseline = _cube_snapshot()
    dynamic = copy.deepcopy(baseline)
    dynamic["rigid_body_enabled"] = True
    result = probe.evaluate_cube_immutability(baseline, [dynamic], [])
    assert result["audit_valid"] is False
    assert "cube_support_contract_invalid" in result["audit_failures"]


def test_event_two_integration_start_contact_must_be_clean():
    trace = _passing_trace()
    trace[14]["contact"]["robot_environment_contact"] = True

    result = probe.evaluate_native_lift_pour_trace(
        trace, retention_steps=60, rise_threshold_m=0.12
    )
    assert result["physical_passed"] is False
    assert "pour_integration_start_robot_environment_contact" in result["physical_failures"]


def test_dynamic_source_accepts_default_scene_membership_but_rejects_wrong_explicit_owner():
    default_owner = _dynamic_source_contract(
        scene_owner=None,
        simulation_owner_targets=[],
    )
    assert probe.evaluate_dynamic_source_contract(default_owner)["audit_valid"] is True

    missing_active_scene = _dynamic_source_contract(
        scene_owner=None,
        simulation_owner_targets=[],
        active_scene_contract={
            "valid": False,
            "physics_context_path": "/physicsScene",
            "physics_scene_paths": ["/physicsScene"],
        },
    )
    result = probe.evaluate_dynamic_source_contract(missing_active_scene)
    assert result["audit_valid"] is False
    assert "source_identity_or_scene_owner_invalid" in result["audit_failures"]

    missing_live_readback = _dynamic_source_contract(
        scene_owner=None,
        simulation_owner_targets=[],
    )
    missing_live_readback["live_physics_membership"]["readbacks"]["world_pose"] = False
    result = probe.evaluate_dynamic_source_contract(missing_live_readback)
    assert result["audit_valid"] is False
    assert "source_identity_or_scene_owner_invalid" in result["audit_failures"]

    wrong_explicit_owner = _dynamic_source_contract(
        scene_owner="/World/notPhysicsScene",
        simulation_owner_targets=["/World/notPhysicsScene"],
    )
    result = probe.evaluate_dynamic_source_contract(wrong_explicit_owner)
    assert result["audit_valid"] is False
    assert "source_identity_or_scene_owner_invalid" in result["audit_failures"]


def test_source_local_com_query_is_safe_pre_reset_and_uses_colliders_mode():
    valid = object()
    colliders_mode = object()

    class SourcePrim:
        def GetPath(self):
            return SOURCE

    class Stage:
        def GetPrimAtPath(self, path):
            assert path == SOURCE
            return SourcePrim()

    class World:
        current_time_step_index = 0

        def is_playing(self):
            return False

    class App:
        update_calls = 0

        def update(self):
            self.update_calls += 1

    class QueryInterface:
        def __init__(self):
            self.kwargs = None

        def query_prim(self, **kwargs):
            self.kwargs = kwargs
            kwargs["rigid_body_fn"](
                SimpleNamespace(
                    result=valid,
                    mass=0.02,
                    center_of_mass=[0.0, 0.0, 0.0],
                    inertia=[0.001, 0.001, 0.001],
                )
            )
            kwargs["finished_fn"]()

    app = App()
    query = QueryInterface()
    result = probe._runtime_source_local_com_authority(
        app,
        Stage(),
        stage_id=7,
        world=World(),
        query_interface=query,
        query_mode=colliders_mode,
        valid_query_result=valid,
        sdf_path_to_int=lambda path: 71 if path == SOURCE else None,
    )

    assert query.kwargs["query_mode"] is colliders_mode
    assert app.update_calls == 0
    assert result["query_timing"] == "pre_task_reset_nonplaying"
    assert result["world_counter_before"] == result["world_counter_after"] == 0
    source = inspect.getsource(probe._runtime_source_local_com_authority)
    assert "QUERY_RIGID_BODY_WITH_COLLIDERS" in source
    assert "QUERY_RIGID_BODY_ONLY" not in source
    assert "world" in inspect.signature(
        probe._runtime_source_local_com_authority
    ).parameters


def test_source_local_com_query_rejects_a_non_prereset_world_before_querying():
    class SourcePrim:
        def GetPath(self):
            return SOURCE

    class Stage:
        def GetPrimAtPath(self, _path):
            return SourcePrim()

    class World:
        current_time_step_index = 1

        def is_playing(self):
            return False

    class QueryInterface:
        def query_prim(self, **_kwargs):
            pytest.fail("pre-reset guard must run before the PhysX query")

    with pytest.raises(
        probe.AuditNoGo,
        match="source_cooked_com_query_unsafe:world_counter_not_pre_reset",
    ):
        probe._runtime_source_local_com_authority(
            object(),
            Stage(),
            stage_id=7,
            world=World(),
            query_interface=QueryInterface(),
            query_mode=object(),
            valid_query_result=object(),
            sdf_path_to_int=lambda _path: 71,
        )


def test_source_local_com_query_rejects_an_update_that_advances_the_world():
    class SourcePrim:
        def GetPath(self):
            return SOURCE

    class Stage:
        def GetPrimAtPath(self, _path):
            return SourcePrim()

    class World:
        current_time_step_index = 0

        def is_playing(self):
            return False

    class App:
        def __init__(self, world):
            self.world = world
            self.update_calls = 0

        def update(self):
            self.update_calls += 1
            self.world.current_time_step_index += 1

    class QueryInterface:
        def query_prim(self, **_kwargs):
            return None

    world = World()
    app = App(world)
    with pytest.raises(
        probe.AuditNoGo,
        match="source_cooked_com_query_unsafe:update_advanced_or_started_world",
    ):
        probe._runtime_source_local_com_authority(
            app,
            Stage(),
            stage_id=7,
            world=world,
            query_interface=QueryInterface(),
            query_mode=object(),
            valid_query_result=object(),
            sdf_path_to_int=lambda _path: 71,
        )
    assert app.update_calls == 1


def test_source_local_com_query_refuses_a_playing_world_before_any_app_update():
    class SourcePrim:
        def GetPath(self):
            return SOURCE

    class Stage:
        def GetPrimAtPath(self, _path):
            return SourcePrim()

    class World:
        current_time_step_index = 0

        def is_playing(self):
            return True

    class App:
        update_calls = 0

        def update(self):
            self.update_calls += 1

    app = App()
    with pytest.raises(probe.AuditNoGo, match="source_cooked_com_query_unsafe"):
        probe._runtime_source_local_com_authority(
            app,
            Stage(),
            stage_id=7,
            world=World(),
            query_interface=object(),
            query_mode=object(),
            valid_query_result=object(),
            sdf_path_to_int=lambda _path: 71,
        )
    assert app.update_calls == 0

    runtime_child_source = inspect.getsource(probe._runtime_child_execute)
    assert runtime_child_source.index("_runtime_source_local_com_authority(") < runtime_child_source.index(
        "task.reset()"
    )


def test_python_closure_covers_data_collectors_and_parent_rejects_self_consistent_child_identity_drift():
    assert probe._internal_module_path("data_collectors.data_collector") == (
        REPO_ROOT / "data_collectors/data_collector.py"
    )

    config = probe.freeze_diagnostic_config(
        CONFIG_PATH,
        production_config_path=PRODUCTION_CONFIG_PATH,
    )["config"]
    parent_identity = probe.build_parent_identity(config)
    child_identity = copy.deepcopy(parent_identity)
    child_identity["runner"]["sha256"] = "c" * 64
    child_identity["identity_sha256"] = probe._canonical_json_sha256(
        {key: value for key, value in child_identity.items() if key != "identity_sha256"}
    )
    runtime_identity = {
        "config_sha256": parent_identity["config_sha256"],
        "parent_static_identity_sha256": child_identity["identity_sha256"],
        "dependency_entry_sha256": parent_identity["asset_dependency_closure"][
            "entry_sha256"
        ],
    }
    runtime_identity["sha256"] = probe._canonical_json_sha256(runtime_identity)
    evidence = {
        "child_static_identity_pre": child_identity,
        "child_static_identity_post": copy.deepcopy(child_identity),
        "runtime_identity_pre": runtime_identity,
        "runtime_identity_post": copy.deepcopy(runtime_identity),
        "dependency_closure": {
            "entry_sha256": parent_identity["asset_dependency_closure"]["entry_sha256"]
        },
        "post_dependency_closure": {
            "entry_sha256": parent_identity["asset_dependency_closure"]["entry_sha256"]
        },
    }

    binding = probe.evaluate_parent_child_identity_binding(
        evidence,
        parent_identity=parent_identity,
        expected_config_sha256=parent_identity["config_sha256"],
    )
    assert binding["audit_valid"] is False
    assert "child_static_identity_parent_mismatch" in binding["audit_failures"]


def test_broad_collision_collection_endpoint_expands_root_partitions_and_unresolved_schema_is_no_go():
    inventory = {
        "relations": [
            {
                "kind": "collision_group",
                "owner_path": "/World/broadCollisionGroup",
                "relationship": "collection:includes",
                "endpoints": ["/World/broadCollisionGroup", "/World"],
                "identity_valid": True,
                "schema_resolution_complete": False,
            }
        ],
        "applied_schemas": [
            {
                "path": "/World/broadCollisionGroup",
                "schemas": ["UsdPhysics.CollisionGroup"],
            },
            {"path": "/World", "schemas": []},
        ],
    }
    result = probe.evaluate_coupling_inventory(inventory)
    assert result["audit_valid"] is False
    assert "unknown_cross_root_collision_treatment" in result["audit_failures"]
    assert "unresolved_cross_root_collision_treatment" in result["audit_failures"]
    assert probe._endpoint_partitions("/World") == {"source", "robot", "support", "other"}


def test_writer_snapshot_after_controller_close_catches_a_close_time_source_write():
    class SourceView:
        def set_world_poses(self, *_args, **_kwargs):
            return None

    class Controller:
        def __init__(self, source_view):
            self.source_view = source_view

        def close(self):
            self.source_view.set_world_poses([[0.0, 0.0, 0.0]], [[1.0, 0.0, 0.0, 0.0]])

    audit = probe._RuntimeWriteAudit()
    source_view = SourceView()
    audit.audit_callable(
        source_view,
        "set_world_poses",
        surface="plural_prim_view_world_poses",
        count=("plural_pose_velocity", "plural_world_poses"),
        source_scoped=False,
        required=True,
    )
    audit.open_epoch()
    Controller(source_view).close()
    snapshot = audit.report(
        mutation_notice_active=True,
        snapshot_phase="after_controller_close",
    )
    assert snapshot["writer_audit_snapshot_phase"] == "after_controller_close"
    assert snapshot["counts"]["plural_world_poses"] == 1


def test_ok_cleanup_requires_non_none_equal_close_counters():
    cleanup = {
        "schema_version": 1,
        "manifest_type": "native_expert_empty_beaker_unbound_lift_cleanup_v1",
        "treatment": "control",
        "run_nonce": "nonce",
        "parent_pid": 123,
        "child_pid": 456,
        "run_id": "run-id",
        "trace_chain_sha256": "a" * 64,
        "controller_closed": True,
        "collector_closed": True,
        "world_counter_before_controller_close": None,
        "world_counter_after_controller_close": None,
        "writer_audit_snapshot_phase": "after_controller_close",
        "writer_audit": {},
        "post_close_mutation_events": [],
        "runtime_status": "ok",
        "lifecycle_status": "measurement_complete_pending_application_close",
    }
    with pytest.raises(ValueError, match="native_unbound_cleanup_receipt_invalid"):
        probe._validate_cleanup_receipt(
            cleanup,
            treatment="control",
            run_nonce="nonce",
            parent_pid=123,
            child_pid=456,
            run_id="run-id",
            trace_chain_sha256="a" * 64,
            runtime_status="ok",
            lifecycle_status="measurement_complete_pending_application_close",
        )


def test_trace_requires_one_first_bootstrap_and_binds_its_runtime_evidence_to_the_report(tmp_path):
    identity = {
        "treatment": "control",
        "run_nonce": "nonce",
        "parent_pid": 123,
        "child_pid": 456,
        "run_id": "run-id",
    }
    malformed = []
    malformed.append(
        probe.make_trace_record(
            malformed, kind="transition", payload={"transition_index": 0}, **identity
        )
    )
    malformed.append(
        probe.make_trace_record(
            malformed, kind="bootstrap", payload={"runtime_evidence": {}}, **identity
        )
    )
    malformed.append(
        probe.make_trace_record(
            malformed,
            kind="terminal",
            payload={
                "runtime_status": "ok",
                "lifecycle_status": "measurement_complete_pending_application_close",
            },
            **identity,
        )
    )
    with pytest.raises(ValueError, match="native_unbound_trace_bootstrap_invalid"):
        probe.validate_trace_records(
            malformed,
            expected_treatment="control",
            expected_nonce="nonce",
            expected_parent_pid=123,
            expected_child_pid=456,
            expected_run_id="run-id",
        )

    artifact_identity = _write_fake_child_artifacts(tmp_path / "child")
    provisional_path = tmp_path / "child" / probe.PROVISIONAL_REPORT_BASENAME
    provisional = probe.load_strict_json_object(provisional_path)
    provisional["runtime_evidence"] = {"changed_after_bootstrap": True}
    provisional_path.write_bytes(probe._canonical_json_bytes(provisional, indent=2))
    with pytest.raises(ValueError, match="native_unbound_trace_runtime_evidence_mismatch"):
        probe._validate_child_artifacts(
            treatment_dir=tmp_path / "child",
            **artifact_identity,
        )


def test_video_validation_requires_decoded_frame_count_to_match_map(monkeypatch, tmp_path):
    video = tmp_path / probe.VIDEO_BASENAME
    video.write_bytes(b"encoded video")
    frame_map = tmp_path / probe.VIDEO_MAP_BASENAME
    probe.atomic_create_json(
        frame_map,
        {
            "schema_version": 1,
            "treatment": "instrumented",
            "run_nonce": "nonce",
            "parent_pid": 123,
            "child_pid": 456,
            "run_id": "run-id",
            "frames": [
                {"video_frame_index": 0, "transition_index": 0, "world_index": 100}
            ],
        },
    )
    video_artifact = probe._artifact_record(video, relative_to=tmp_path)
    map_artifact = probe._artifact_record(frame_map, relative_to=tmp_path)
    provisional = {
        "treatment": "instrumented",
        "run_nonce": "nonce",
        "parent_pid": 123,
        "child_pid": 456,
        "run_id": "run-id",
        "runtime_evidence": {
            "video_sample_every_transitions": 2,
            "video_artifacts": {
                "video": video_artifact,
                "frame_map": map_artifact,
                "frame_count": 1,
            },
        },
        "artifacts": {"video": video_artifact, "video_frame_map": map_artifact},
    }
    monkeypatch.setattr(probe, "_decoded_video_frame_count", lambda _path: 2)
    with pytest.raises(ValueError, match="native_unbound_video_decoded_frame_count_mismatch"):
        probe._validate_video_artifacts(
            tmp_path,
            provisional,
            trace_records=[
                {
                    "kind": "transition",
                    "payload": {
                        "transition_index": 0,
                        "world_index": 100,
                        "state_present": True,
                    },
                }
            ],
        )


def test_cube_descendant_static_state_and_pour_path_remain_continuously_clean():
    cube = _cube_snapshot()
    dynamic_cube = copy.deepcopy(cube)
    dynamic_cube["descendant_physics_state"]["body_state"][SUPPORT] = {
        "rigid_body_api": True,
        "rigid_body_enabled": True,
        "kinematic_enabled": False,
    }
    cube_result = probe.evaluate_cube_immutability(cube, [dynamic_cube], [])
    assert cube_result["audit_valid"] is False
    assert "cube_support_contract_invalid" in cube_result["audit_failures"]

    trace = _passing_trace()
    trace[15]["contact"]["source_support_recontact"] = True
    pour_result = probe.evaluate_native_lift_pour_trace(
        trace, retention_steps=60, rise_threshold_m=0.12
    )
    assert pour_result["physical_passed"] is False
    assert "pour_rotation_support_recontact" in pour_result["physical_failures"]


def test_post_terminal_continuation_cannot_carry_an_apply_index_without_an_action():
    terminal = _action_record(0)
    terminal["production_terminal"] = True
    terminal["terminal_outcome"] = "FINISHED"
    terminal["terminal_success"] = True
    continuation = _action_record(
        1,
        phase_before="FINISHED",
        phase_after="FINISHED",
        state_present=False,
        continuation_index=0,
    )
    continuation["apply_index"] = 0
    result = probe.evaluate_action_ledger([terminal, continuation], maximum_production_steps=1500)
    assert result["audit_valid"] is False
    assert "continuation_action_forbidden" in result["audit_failures"]
