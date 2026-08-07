from __future__ import annotations

from utils import formal_precontact_event0_replay as replay


def _contract() -> dict:
    payload = {
        "authority": replay.AUTHORITY,
        "classification": "FORMAL_PRECONTACT_EVENT0_REPLAY_ONLY",
        "schema_version": 1,
        "pre_roll_steps": 600,
        "transition_count": 6,
        "v7_config_sha256": "a" * 64,
        "local_scene_sha256": "b" * 64,
        "local_franka_sha256": "c" * 64,
        "hidden_cube_overlay_sha256": "d" * 64,
        "forbidden_operations": ["close", "attachment", "lift", "contact_observer", "phase3", "gate"],
    }
    return {**payload, "sha256": replay.canonical_json_sha256(payload)}


def _transition(index: int, action: dict | None = None) -> dict:
    action_hash = replay.canonical_json_sha256(action) if action is not None else None
    pick = {
        "start": True,
        "event": 0,
        "last_emitted_event": None,
        "close": False,
        "lift": False,
    }
    if index == 4:
        pick["start"] = False
    if index == 5:
        pick["start"] = False
        pick["last_emitted_event"] = 0
    return {
        "transition_index": index,
        "world_index_before": 1300 + 2 * index,
        "world_index_after": 1302 + 2 * index,
        "task_frame_idx": index + 1,
        "controller_called": index >= 4,
        "raw_action": action,
        "raw_action_sha256": action_hash,
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


def _trace(event0_positions: list[float]) -> dict:
    opening = {
        "joint_positions": [None] * 7 + [0.04, 0.04],
        "joint_velocities": None,
        "joint_efforts": None,
        "joint_indices": None,
    }
    event0 = {
        "joint_positions": event0_positions,
        "joint_velocities": [0.0] * 7,
        "joint_efforts": None,
        "joint_indices": list(range(7)),
    }
    transitions = [_transition(index) for index in range(4)]
    transitions.append(_transition(4, opening))
    transitions.append(_transition(5, event0))
    event0_in_limits = all(-3.0 <= value <= 3.0 for value in event0_positions)
    if not event0_in_limits:
        transitions[-1]["apply_count"] = 0
    return {
        "schema_version": 1,
        "authority": replay.AUTHORITY,
        "pre_roll": {
            "requested_steps": 600,
            "world_index_before": 100,
            "world_index_after": 1300,
            "world_step_call_count": 600,
        },
        "transitions": transitions,
        "terminal": {
            "world_index": 1312,
            "event0_action_applied": event0_in_limits,
            "event0_integrated": False,
            "close": False,
            "lift": False,
            "phase": "PICKING",
        },
    }


def test_precontact_event0_replay_accepts_a_multi_tick_world_step_cadence():
    evaluation = replay.evaluate_precontact_event0_replay(_trace([0.1] * 7), _contract())

    assert evaluation["decision"] == replay.PASS
    assert evaluation["event0_position_limit_violations"] == []
    assert evaluation["pre_roll_world_step_call_count"] == 600
    assert evaluation["pre_roll_world_index_delta"] == 1200


def test_precontact_event0_replay_reports_native_limit_no_go():
    evaluation = replay.evaluate_precontact_event0_replay(
        _trace([0.1, 0.1, 0.1, -4.0, 0.1, 4.0, 0.1]), _contract()
    )

    assert evaluation["decision"] == replay.NO_GO
    assert [item["index"] for item in evaluation["event0_position_limit_violations"]] == [3, 5]


def test_precontact_event0_replay_rejects_a_close_or_extra_action():
    trace = _trace([0.1] * 7)
    trace["transitions"][5]["pick"]["close"] = True

    evaluation = replay.evaluate_precontact_event0_replay(trace, _contract())

    assert evaluation == {
        "decision": replay.SAFETY_ABORT,
        "validation_error": "precontact_replay_transition_invalid",
    }
