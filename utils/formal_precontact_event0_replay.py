"""Pure validation for the formal production-like prefix through native event 0.

This evidence is a bounded controller-lifecycle diagnostic. It cannot authorize
grasp contact, attachment, lift, pouring, a gate, or Phase 3.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any


AUTHORITY = "formal_precontact_event0_replay_v1"
PASS = "FORMAL_PRECONTACT_EVENT0_PASS"
NO_GO = "PRECONTACT_NO_GO"
SAFETY_ABORT = "SAFETY_ABORT"


def canonical_json_sha256(value: Any) -> str:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("precontact_replay_json_invalid") from exc
    return hashlib.sha256(payload).hexdigest()


def _vector(value: Any, *, field: str, length: int) -> list[float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != length:
        raise ValueError(f"precontact_replay_{field}_invalid")
    result = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"precontact_replay_{field}_invalid")
        numeric = float(item)
        if not math.isfinite(numeric):
            raise ValueError(f"precontact_replay_{field}_invalid")
        result.append(numeric)
    return result


def _raw_action(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "joint_positions",
        "joint_velocities",
        "joint_efforts",
        "joint_indices",
    }:
        raise ValueError(f"precontact_replay_{field}_invalid")

    def channel(raw: Any, *, sparse: bool) -> list[float | None] | None:
        if raw is None:
            return None
        if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
            raise ValueError(f"precontact_replay_{field}_invalid")
        result: list[float | None] = []
        for item in raw:
            if item is None and sparse:
                result.append(None)
                continue
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise ValueError(f"precontact_replay_{field}_invalid")
            numeric = float(item)
            if not math.isfinite(numeric):
                raise ValueError(f"precontact_replay_{field}_invalid")
            result.append(numeric)
        return result

    indices = value["joint_indices"]
    if indices is not None:
        if isinstance(indices, (str, bytes)) or not isinstance(indices, Sequence):
            raise ValueError(f"precontact_replay_{field}_invalid")
        indices = list(indices)
        if any(type(index) is not int for index in indices):
            raise ValueError(f"precontact_replay_{field}_invalid")
    return {
        "joint_positions": channel(value["joint_positions"], sparse=True),
        "joint_velocities": channel(value["joint_velocities"], sparse=False),
        "joint_efforts": channel(value["joint_efforts"], sparse=False),
        "joint_indices": indices,
    }


def _transition(value: Any, *, index: int) -> dict[str, Any]:
    required = {
        "transition_index",
        "world_index_before",
        "world_index_after",
        "task_frame_idx",
        "controller_called",
        "raw_action",
        "raw_action_sha256",
        "apply_count",
        "pick",
        "controller_phase",
        "pour_forward_invocation_count",
        "joint_positions_before_action",
        "joint_velocities_before_action",
        "joint_lower_limits",
        "joint_upper_limits",
        "source_position",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError("precontact_replay_transition_invalid")
    if (
        value["transition_index"] != index
        or type(value["world_index_before"]) is not int
        or type(value["world_index_after"]) is not int
        or value["world_index_after"] <= value["world_index_before"]
        or value["task_frame_idx"] != index + 1
        or type(value["controller_called"]) is not bool
        or type(value["apply_count"]) is not int
        or value["apply_count"] not in {0, 1}
        or value["controller_phase"] != "PICKING"
        or value["pour_forward_invocation_count"] != 0
    ):
        raise ValueError("precontact_replay_transition_invalid")
    pick = value["pick"]
    if (
        not isinstance(pick, Mapping)
        or set(pick) != {"start", "event", "last_emitted_event", "close", "lift"}
        or type(pick["start"]) is not bool
        or type(pick["event"]) is not int
        or pick["event"] < 0
        or pick["event"] > 1
        or pick["last_emitted_event"] not in {None, 0}
        or pick["close"] is not False
        or pick["lift"] is not False
    ):
        raise ValueError("precontact_replay_transition_invalid")
    action = value["raw_action"]
    if action is None:
        if value["raw_action_sha256"] is not None or value["apply_count"] != 0:
            raise ValueError("precontact_replay_transition_invalid")
    else:
        action = _raw_action(action, field="action")
        if (
            value["raw_action_sha256"] != canonical_json_sha256(action)
        ):
            raise ValueError("precontact_replay_transition_invalid")
    return {
        **dict(value),
        "raw_action": action,
        "joint_positions_before_action": _vector(
            value["joint_positions_before_action"], field="joint_positions", length=9
        ),
        "joint_velocities_before_action": _vector(
            value["joint_velocities_before_action"], field="joint_velocities", length=9
        ),
        "joint_lower_limits": _vector(value["joint_lower_limits"], field="lower", length=9),
        "joint_upper_limits": _vector(value["joint_upper_limits"], field="upper", length=9),
        "source_position": _vector(value["source_position"], field="source_position", length=3),
    }


def _evaluate(trace: Any, contract: Any) -> dict[str, Any]:
    if not isinstance(contract, Mapping) or set(contract) != {
        "authority",
        "classification",
        "schema_version",
        "pre_roll_steps",
        "transition_count",
        "v7_config_sha256",
        "local_scene_sha256",
        "local_franka_sha256",
        "hidden_cube_overlay_sha256",
        "forbidden_operations",
        "sha256",
    }:
        raise ValueError("precontact_replay_contract_invalid")
    if (
        contract["authority"] != AUTHORITY
        or contract["classification"] != "FORMAL_PRECONTACT_EVENT0_REPLAY_ONLY"
        or contract["schema_version"] != 1
        or type(contract["pre_roll_steps"]) is not int
        or contract["pre_roll_steps"] <= 0
        or contract["transition_count"] != 6
        or not isinstance(contract["v7_config_sha256"], str)
        or not all(
            isinstance(contract[field], str) and len(contract[field]) == 64
            for field in (
                "v7_config_sha256",
                "local_scene_sha256",
                "local_franka_sha256",
                "hidden_cube_overlay_sha256",
            )
        )
        or contract["forbidden_operations"]
        != ["close", "attachment", "lift", "contact_observer", "phase3", "gate"]
        or contract["sha256"]
        != canonical_json_sha256({key: value for key, value in contract.items() if key != "sha256"})
    ):
        raise ValueError("precontact_replay_contract_invalid")
    if not isinstance(trace, Mapping) or set(trace) != {
        "schema_version",
        "authority",
        "pre_roll",
        "transitions",
        "terminal",
    }:
        raise ValueError("precontact_replay_trace_invalid")
    if trace["schema_version"] != 1 or trace["authority"] != AUTHORITY:
        raise ValueError("precontact_replay_trace_invalid")
    pre_roll = trace["pre_roll"]
    if (
        not isinstance(pre_roll, Mapping)
        or set(pre_roll)
        != {
            "requested_steps",
            "world_step_call_count",
            "world_index_before",
            "world_index_after",
        }
        or pre_roll["requested_steps"] != contract["pre_roll_steps"]
        or pre_roll["world_step_call_count"] != contract["pre_roll_steps"]
        or type(pre_roll["world_step_call_count"]) is not int
        or type(pre_roll["world_index_before"]) is not int
        or type(pre_roll["world_index_after"]) is not int
        or pre_roll["world_index_after"] <= pre_roll["world_index_before"]
    ):
        raise ValueError("precontact_replay_pre_roll_invalid")
    transitions = trace["transitions"]
    if not isinstance(transitions, list) or len(transitions) != contract["transition_count"]:
        raise ValueError("precontact_replay_trace_invalid")
    normalized = [_transition(item, index=index) for index, item in enumerate(transitions)]
    if normalized[0]["world_index_before"] != pre_roll["world_index_after"]:
        raise ValueError("precontact_replay_trace_invalid")
    for prior, current in zip(normalized, normalized[1:]):
        if current["world_index_before"] != prior["world_index_after"]:
            raise ValueError("precontact_replay_trace_invalid")
    for record in normalized[:4]:
        if record["controller_called"] or record["raw_action"] is not None:
            raise ValueError("precontact_replay_frame_gate_invalid")
    opening = normalized[4]
    opening_action = opening["raw_action"]
    if (
        opening["controller_called"] is not True
        or opening["apply_count"] != 1
        or opening["pick"] != {
            "start": False,
            "event": 0,
            "last_emitted_event": None,
            "close": False,
            "lift": False,
        }
        or not isinstance(opening_action, Mapping)
        or opening_action["joint_indices"] is not None
        or opening_action["joint_velocities"] is not None
        or opening_action["joint_efforts"] is not None
        or opening_action["joint_positions"] is None
        or len(opening_action["joint_positions"]) != 9
        or any(value is not None for value in opening_action["joint_positions"][:7])
        or any(value is None for value in opening_action["joint_positions"][7:])
    ):
        raise ValueError("precontact_replay_opening_invalid")
    event0 = normalized[5]
    event0_action = event0["raw_action"]
    if (
        event0["controller_called"] is not True
        or event0["pick"]["last_emitted_event"] != 0
        or not isinstance(event0_action, Mapping)
        or not isinstance(event0_action["joint_positions"], list)
        or not isinstance(event0_action["joint_velocities"], list)
        or event0_action["joint_efforts"] is not None
        or event0_action["joint_indices"] != list(range(7))
        or len(event0_action["joint_positions"]) != 7
        or len(event0_action["joint_velocities"]) != 7
        or any(value is None for value in event0_action["joint_positions"])
    ):
        raise ValueError("precontact_replay_event0_invalid")
    terminal = trace["terminal"]
    if (
        not isinstance(terminal, Mapping)
        or set(terminal)
        != {"world_index", "event0_action_applied", "event0_integrated", "close", "lift", "phase"}
        or terminal["world_index"] != event0["world_index_after"]
        or terminal["event0_integrated"] is not False
        or terminal["close"] is not False
        or terminal["lift"] is not False
        or terminal["phase"] != "PICKING"
    ):
        raise ValueError("precontact_replay_terminal_invalid")
    target = list(event0["joint_positions_before_action"])
    for index, value in zip(event0_action["joint_indices"], event0_action["joint_positions"], strict=True):
        target[index] = float(value)
    violations = [
        {
            "index": index,
            "target": target[index],
            "lower": event0["joint_lower_limits"][index],
            "upper": event0["joint_upper_limits"][index],
        }
        for index in event0_action["joint_indices"]
        if target[index] < event0["joint_lower_limits"][index]
        or target[index] > event0["joint_upper_limits"][index]
    ]
    common = {
        "event0_raw_action_sha256": event0["raw_action_sha256"],
        "event0_resolved_position_target": target,
        "event0_resolved_position_target_sha256": canonical_json_sha256(target),
        "event0_position_limit_violations": violations,
        "pre_roll_world_step_call_count": pre_roll["world_step_call_count"],
        "pre_roll_world_index_delta": pre_roll["world_index_after"] - pre_roll["world_index_before"],
        "terminal_world_index": terminal["world_index"],
    }
    if violations:
        if terminal["event0_action_applied"] is not False or event0["apply_count"] != 0:
            raise ValueError("precontact_replay_terminal_invalid")
        return {"decision": NO_GO, **common}
    if terminal["event0_action_applied"] is not True or event0["apply_count"] != 1:
        raise ValueError("precontact_replay_terminal_invalid")
    return {"decision": PASS, **common}


def evaluate_precontact_event0_replay(trace: Any, contract: Any) -> dict[str, Any]:
    try:
        return _evaluate(trace, contract)
    except ValueError as exc:
        return {"decision": SAFETY_ABORT, "validation_error": str(exc)}
