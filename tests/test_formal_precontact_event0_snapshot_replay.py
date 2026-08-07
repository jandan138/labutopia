from __future__ import annotations

from utils import formal_precontact_event0_replay as replay
from utils import formal_precontact_event0_snapshot_replay as snapshot


IDENTITY = [
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
]


def _contract() -> dict:
    source_snapshot = {
        "authority": snapshot.SOURCE_CLOSURE_AUTHORITY,
        "matrix_convention": snapshot.MATRIX_CONVENTION,
        "source_root_path": "/World/beaker2",
        "source_mesh_path": "/World/beaker2/mesh",
        "source_wrapper_root_path": "/World/beaker2/FluidSafeWrapperCanonical",
        "expected_external_shell_count": 1,
        "expected_internal_wrapper_count": 145,
        "usd_witness_matrix_atol": 1.0e-8,
    }
    payload = {
        "authority": snapshot.AUTHORITY,
        "classification": snapshot.CLASSIFICATION,
        "schema_version": 2,
        "pre_roll_steps": 600,
        "transition_count": 6,
        "v7_config_sha256": "a" * 64,
        "local_scene_sha256": "b" * 64,
        "local_franka_sha256": "c" * 64,
        "hidden_cube_overlay_sha256": "d" * 64,
        "forbidden_operations": ["close", "attachment", "lift", "contact_observer", "phase3", "gate"],
        "source_snapshot": source_snapshot,
    }
    return {**payload, "sha256": replay.canonical_json_sha256(payload)}


def _transition(index: int, action: dict | None = None) -> dict:
    pick = {
        "start": True,
        "event": 0,
        "last_emitted_event": None,
        "close": False,
        "lift": False,
    }
    if index >= 4:
        pick["start"] = False
    if index == 5:
        pick["last_emitted_event"] = 0
    return {
        "transition_index": index,
        "world_index_before": 1300 + 2 * index,
        "world_index_after": 1302 + 2 * index,
        "task_frame_idx": index + 1,
        "controller_called": index >= 4,
        "raw_action": action,
        "raw_action_sha256": replay.canonical_json_sha256(action) if action is not None else None,
        "apply_count": 1 if action is not None else 0,
        "pick": pick,
        "controller_phase": "PICKING",
        "pour_forward_invocation_count": 0,
        "joint_positions_before_action": [0.0] * 9,
        "joint_velocities_before_action": [0.0] * 9,
        "joint_lower_limits": [-3.0] * 9,
        "joint_upper_limits": [3.0] * 9,
        "source_position": [0.3, 0.1, 0.8],
    }


def _closure(event0_action_sha256: str, target_sha256: str) -> dict:
    colliders = [
        {
            "path": "/World/beaker2/mesh",
            "role": "external_shell",
            "collision_enabled": True,
            "rigid_owner_path": "/World/beaker2",
            "collider_to_source_root_row_major": IDENTITY,
            "usd_world_matrix_row_major": IDENTITY,
            "composed_world_matrix_row_major": IDENTITY,
        }
    ]
    colliders.extend(
        {
            "path": f"/World/beaker2/FluidSafeWrapperCanonical/Wall_{index:03d}",
            "role": "internal_wrapper",
            "collision_enabled": True,
            "rigid_owner_path": "/World/beaker2",
            "collider_to_source_root_row_major": IDENTITY,
            "usd_world_matrix_row_major": IDENTITY,
            "composed_world_matrix_row_major": IDENTITY,
        }
        for index in range(145)
    )
    colliders.sort(key=lambda collider: collider["path"])
    payload = {
        "authority": snapshot.SOURCE_CLOSURE_AUTHORITY,
        "matrix_convention": snapshot.MATRIX_CONVENTION,
        "source_root_path": "/World/beaker2",
        "capture": {
            "transition_index": 5,
            "world_index_after_transition": 1312,
            "task_frame_idx": 6,
            "event0_raw_action_sha256": event0_action_sha256,
            "event0_resolved_position_target_sha256": target_sha256,
            "event0_apply_count_at_capture": 0,
            "world_index_after_capture": 1312,
        },
        "source_root": {
            "physx_world_matrix_row_major": IDENTITY,
            "usd_world_matrix_row_major": IDENTITY,
            "linear_velocity_m_s": [0.0, 0.0, 0.0],
            "angular_velocity_rad_s": [0.0, 0.0, 0.0],
        },
        "colliders": colliders,
    }
    return {**payload, "sha256": replay.canonical_json_sha256(payload)}


def _trace() -> dict:
    opening = {
        "joint_positions": [None] * 7 + [0.04, 0.04],
        "joint_velocities": None,
        "joint_efforts": None,
        "joint_indices": None,
    }
    event0 = {
        "joint_positions": [0.1] * 7,
        "joint_velocities": [0.0] * 7,
        "joint_efforts": None,
        "joint_indices": list(range(7)),
    }
    transitions = [_transition(index) for index in range(4)]
    transitions.extend([_transition(4, opening), _transition(5, event0)])
    target_sha256 = replay.canonical_json_sha256([0.1] * 7 + [0.0, 0.0])
    return {
        "schema_version": 2,
        "authority": snapshot.AUTHORITY,
        "pre_roll": {
            "requested_steps": 600,
            "world_step_call_count": 600,
            "world_index_before": 100,
            "world_index_after": 1300,
        },
        "transitions": transitions,
        "terminal": {
            "world_index": 1312,
            "event0_action_applied": True,
            "event0_integrated": False,
            "close": False,
            "lift": False,
            "phase": "PICKING",
            "source_collider_closure": _closure(
                replay.canonical_json_sha256(event0), target_sha256
            ),
        },
    }


def test_snapshot_trace_accepts_exact_event0_collider_closure():
    trace = _trace()

    evaluation = snapshot.evaluate_precontact_event0_snapshot_replay(trace, _contract())

    assert evaluation["decision"] == snapshot.PASS
    assert evaluation["source_collider_count"] == 146
    assert evaluation["source_collider_closure_sha256"] == trace["terminal"]["source_collider_closure"]["sha256"]


def test_snapshot_trace_rejects_a_composed_collider_matrix_drift():
    trace = _trace()
    closure = trace["terminal"]["source_collider_closure"]
    closure["colliders"][0]["composed_world_matrix_row_major"] = [
        *IDENTITY[:12],
        0.01,
        0.0,
        0.0,
        1.0,
    ]
    payload = {key: value for key, value in closure.items() if key != "sha256"}
    closure["sha256"] = replay.canonical_json_sha256(payload)

    evaluation = snapshot.evaluate_precontact_event0_snapshot_replay(trace, _contract())

    assert evaluation == {
        "decision": snapshot.SAFETY_ABORT,
        "validation_error": "precontact_snapshot_closure_matrix_invalid",
    }


def test_snapshot_trace_rejects_a_scaled_physx_source_root():
    trace = _trace()
    closure = trace["terminal"]["source_collider_closure"]
    scaled = [2.0, *IDENTITY[1:]]
    closure["source_root"]["physx_world_matrix_row_major"] = scaled
    closure["source_root"]["usd_world_matrix_row_major"] = scaled
    for collider in closure["colliders"]:
        collider["usd_world_matrix_row_major"] = scaled
        collider["composed_world_matrix_row_major"] = scaled
    payload = {key: value for key, value in closure.items() if key != "sha256"}
    closure["sha256"] = replay.canonical_json_sha256(payload)

    evaluation = snapshot.evaluate_precontact_event0_snapshot_replay(trace, _contract())

    assert evaluation == {
        "decision": snapshot.SAFETY_ABORT,
        "validation_error": "precontact_snapshot_closure_root_not_rigid",
    }


def _fixed_mount_profile() -> dict:
    return {
        "authority": snapshot.FIXED_MOUNT_PROFILE_AUTHORITY,
        "schema_version": 1,
        "profile_id": "v7_link0_table_surface_mount_filter_v1",
        "profile_path": "config/formal_precontact_fixed_mount_filter_v1.json",
        "profile_sha256": "e" * 64,
        "robot_position_m": [-0.4, 0.0, 0.772761],
        "filter": {
            "overlay_path": (
                "assets/chemistry_lab/lab_001_fluid_eval/"
                "lab_001_v7_link0_table_fixed_mount_filter_v1.usda"
            ),
            "overlay_sha256": "f" * 64,
            "author_collider_path": "/World/Franka/panda_link0/geometry/panda_link0",
            "target_collider_path": "/World/table/surface/mesh",
        },
    }


def test_fixed_mount_snapshot_contract_binds_only_the_approved_pair():
    profile = _fixed_mount_profile()
    contract = snapshot.build_fixed_mount_contract(
        pre_roll_steps=600,
        v7_config_sha256="a" * 64,
        local_scene_sha256="b" * 64,
        local_franka_sha256="c" * 64,
        hidden_cube_overlay_sha256="d" * 64,
        fixed_mount_profile=profile,
    )
    trace = _trace()
    trace["schema_version"] = 3
    trace["authority"] = snapshot.FIXED_MOUNT_AUTHORITY
    trace["terminal"]["fixed_mount_filter"] = {
        "authority": snapshot.FIXED_MOUNT_RUNTIME_FILTER_AUTHORITY,
        "profile_sha256": profile["profile_sha256"],
        "author_collider_path": profile["filter"]["author_collider_path"],
        "target_collider_path": profile["filter"]["target_collider_path"],
        "filtered_pair": sorted(
            [
                profile["filter"]["author_collider_path"],
                profile["filter"]["target_collider_path"],
            ]
        ),
        "authored_filtered_pair_paths": [
            [
                profile["filter"]["author_collider_path"],
                profile["filter"]["target_collider_path"],
            ]
        ],
        "robot_filtered_pair_paths": [
            [
                profile["filter"]["author_collider_path"],
                profile["filter"]["target_collider_path"],
            ]
        ],
        "collision_group_membership_paths": [],
    }

    evaluation = snapshot.evaluate_precontact_event0_snapshot_replay(trace, contract)

    assert evaluation["decision"] == snapshot.PASS
    assert evaluation["fixed_mount_profile_sha256"] == profile["profile_sha256"]


def test_fixed_mount_snapshot_rejects_a_broader_runtime_filter():
    profile = _fixed_mount_profile()
    contract = snapshot.build_fixed_mount_contract(
        pre_roll_steps=600,
        v7_config_sha256="a" * 64,
        local_scene_sha256="b" * 64,
        local_franka_sha256="c" * 64,
        hidden_cube_overlay_sha256="d" * 64,
        fixed_mount_profile=profile,
    )
    trace = _trace()
    trace["schema_version"] = 3
    trace["authority"] = snapshot.FIXED_MOUNT_AUTHORITY
    trace["terminal"]["fixed_mount_filter"] = {
        "authority": snapshot.FIXED_MOUNT_RUNTIME_FILTER_AUTHORITY,
        "profile_sha256": profile["profile_sha256"],
        "author_collider_path": "/World/Franka/panda_link0",
        "target_collider_path": profile["filter"]["target_collider_path"],
        "filtered_pair": sorted(
            [
                profile["filter"]["author_collider_path"],
                profile["filter"]["target_collider_path"],
            ]
        ),
        "authored_filtered_pair_paths": [
            [
                "/World/Franka/panda_link0",
                profile["filter"]["target_collider_path"],
            ]
        ],
        "robot_filtered_pair_paths": [
            [
                "/World/Franka/panda_link0",
                profile["filter"]["target_collider_path"],
            ]
        ],
        "collision_group_membership_paths": [],
    }

    evaluation = snapshot.evaluate_precontact_event0_snapshot_replay(trace, contract)

    assert evaluation == {
        "decision": snapshot.SAFETY_ABORT,
        "validation_error": "precontact_fixed_mount_filter_invalid",
    }
