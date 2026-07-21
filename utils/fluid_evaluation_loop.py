"""Strict model-facing orchestration for online physics-driven liquid surfaces."""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
import os
import time
import uuid
from collections.abc import Mapping, Sequence
from itertools import count
from pathlib import Path
from typing import Any, Callable

import numpy as np

from utils.controlled_contact import (
    build_precontact_continuation_lease,
    canonical_json_sha256,
    validate_target_token,
)
from utils.online_fluid_surface import (
    ObservationTransition,
    OnlineFluidSurfaceRuntime,
    SurfaceFrameToken,
    validate_simulation_points,
)


_NO_PENDING_ACTION = object()
_TERMINAL_ACTION_UNSET = object()
_PROCESS_RUN_ID = uuid.uuid4().hex
_PROCESS_ATTEMPT_INDICES = count()
_PROCESS_SAMPLE_INDICES = count()
_ATTEMPT_STATUSES = frozenset({"completed", "failed", "interrupted"})
_CONTACT_ACQUISITION_PROBE_CONTROL_CONTRACT_ID = (
    "contact_acquisition_probe_control_v1"
)
_CONTACT_ACQUISITION_PROBE_CONTROL_CONTRACT_VERSION = 1
_CONTACT_ACQUISITION_PROBE_PROFILES = (
    "native_expert_v1",
    "contact_pick_v1",
)
_PARTITION_FIELDS = (
    "source",
    "target",
    "transit",
    "tabletop_spill",
    "below_table",
    "nonfinite",
)
_NON_SOURCE_PARTITION_FIELDS = _PARTITION_FIELDS[1:]
_EVIDENCE_LEDGER_CACHE: dict[
    tuple[str, Path], tuple[tuple[int, int, int], set[tuple[Any, ...]]]
] = {}
_ACTION_FIELDS = (
    "joint_positions",
    "joint_velocities",
    "joint_efforts",
    "joint_indices",
)
_CONTROLLED_TERMINAL_KINDS = frozenset(
    {
        "PHYSICAL_CONTACT_FAILURE",
        "PHYSICAL_MOTION_FAILURE",
        "PHYSICAL_PARTICLE_FAILURE",
        "PHYSICAL_TIMEOUT",
        "PROTOCOL_FAILURE",
    }
)
_CONTROLLED_PREPHYSICS_STAGES = frozenset(
    {
        "preaction_authority",
        "controller_step",
        "action_context",
        "proposal_validation",
        "commit",
        "apply",
        "receipt_integrity",
        "receipt_confirmation",
        "action_logging",
    }
)
_CONTROLLED_APPLICATION_OUTCOMES = frozenset(
    {
        "not_invoked",
        "invoked_outcome_unknown",
        "normal_return_unconfirmed",
        "confirmed_applied",
    }
)


def _controlled_application_outcome(
    *,
    callback_entered: bool,
    callback_normal_return: bool,
    candidate_receipt: Mapping[str, Any] | None,
    confirmed_receipt: Mapping[str, Any] | None,
) -> str:
    if type(callback_entered) is not bool or type(callback_normal_return) is not bool:
        raise ValueError("controlled_terminal_transaction_invalid")
    if callback_normal_return and not callback_entered:
        raise ValueError("controlled_terminal_transaction_invalid")
    if candidate_receipt is not None and not callback_normal_return:
        raise ValueError("controlled_terminal_transaction_invalid")
    if confirmed_receipt is not None and candidate_receipt is None:
        raise ValueError("controlled_terminal_transaction_invalid")
    if confirmed_receipt is not None:
        return "confirmed_applied"
    if callback_normal_return:
        return "normal_return_unconfirmed"
    if callback_entered:
        return "invoked_outcome_unknown"
    return "not_invoked"


def validate_controlled_terminal_transition(
    terminal: Mapping[str, Any],
) -> dict[str, bool]:
    if not isinstance(terminal, Mapping):
        raise TypeError("controlled_terminal_transition_mapping_required")
    value = copy.deepcopy(dict(terminal))
    digest = value.pop("sha256", None)
    if (
        value.get("authority") != "controlled_terminal_transition_v1"
        or digest != canonical_json_sha256(value)
    ):
        raise ValueError("controlled_terminal_transition_hash_invalid")
    decision = value.get("decision")
    if not isinstance(decision, Mapping):
        raise ValueError("controlled_terminal_transition_decision_invalid")
    transaction = decision.get("transaction")
    if transaction is None:
        return {"requires_world_termination": False}
    if not isinstance(transaction, Mapping):
        raise ValueError("controlled_terminal_transaction_invalid")
    candidate = transaction.get("candidate_receipt")
    confirmed = transaction.get("confirmed_receipt")
    if candidate is not None and not isinstance(candidate, Mapping):
        raise ValueError("controlled_terminal_transaction_invalid")
    if confirmed is not None and not isinstance(confirmed, Mapping):
        raise ValueError("controlled_terminal_transaction_invalid")
    derived_outcome = _controlled_application_outcome(
        callback_entered=transaction.get("apply_callback_entered"),
        callback_normal_return=transaction.get("apply_callback_normal_return"),
        candidate_receipt=candidate,
        confirmed_receipt=confirmed,
    )
    requires_termination = bool(
        transaction.get("apply_callback_entered")
        or candidate is not None
        or confirmed is not None
    )
    if (
        transaction.get("authority")
        != "controlled_prephysics_transaction_failure_v1"
        or transaction.get("application_outcome") != derived_outcome
        or transaction.get("requires_world_termination")
        is not requires_termination
        or transaction.get("physics_step_delta") != 0
        or transaction.get("simulation_time_delta") != 0.0
    ):
        raise ValueError("controlled_terminal_transaction_invalid")
    return {"requires_world_termination": requires_termination}


def _action_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("action_nonfinite")
        return value
    if isinstance(value, np.generic):
        return _action_json_value(value.item())
    if isinstance(value, np.ndarray):
        if np.issubdtype(value.dtype, np.number) and not np.isfinite(value).all():
            raise ValueError("action_nonfinite")
        contiguous = np.ascontiguousarray(value)
        return {
            "dtype": contiguous.dtype.str,
            "shape": list(contiguous.shape),
            "values": contiguous.tolist(),
        }
    if isinstance(value, Mapping):
        return {
            str(key): _action_json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_action_json_value(item) for item in value]

    fields = {
        name: _action_json_value(getattr(value, name))
        for name in _ACTION_FIELDS
        if hasattr(value, name)
    }
    if fields:
        return {
            "action_type": f"{type(value).__module__}.{type(value).__qualname__}",
            "fields": fields,
        }
    raise TypeError(f"action_not_canonicalizable:{type(value).__qualname__}")


def canonical_action_sha256(action: Any) -> str:
    payload = {"kind": "noop"} if action is None else {
        "kind": "action",
        "value": _action_json_value(action),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


_CONTROLLED_PHASE_ACTION_KINDS = {
    "PREGRASP": frozenset({"GRIPPER_OPEN", "ARM_PREGRASP"}),
    "ALIGN": frozenset({"ARM_ALIGN"}),
    "INSERT": frozenset({"ARM_INSERT"}),
    "SETTLE": frozenset({"ARM_SETTLE"}),
    "PRECONTACT_SETTLE": frozenset({"ARM_PRECONTACT_SETTLE"}),
    "CLOSE": frozenset({"GRIPPER_CLOSE"}),
    "CONTACT_SETTLE": frozenset({"GRIPPER_CONTACT_SETTLE"}),
}
_CONTROLLED_ACTION_KINDS = frozenset(
    kind for kinds in _CONTROLLED_PHASE_ACTION_KINDS.values() for kind in kinds
)


def _controlled_action_vector(
    value: Any,
    *,
    allow_none: bool,
) -> list[Any]:
    if isinstance(value, np.ndarray):
        if value.ndim != 1:
            raise RuntimeError("controlled_action_channel_invalid")
        result = value.tolist()
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        result = list(value)
    else:
        raise RuntimeError("controlled_action_channel_invalid")
    if not result:
        raise RuntimeError("controlled_action_channel_invalid")
    for item in result:
        if item is None and allow_none:
            continue
        if (
            item is None
            or isinstance(item, bool)
            or not isinstance(item, (int, float, np.number))
            or not math.isfinite(float(item))
        ):
            raise RuntimeError("controlled_action_channel_invalid")
    return result


def _controlled_action_validation(
    *,
    action: Any,
    phase: str,
    semantic_action_kind: str,
    terminal_latched: bool,
    finger_joint_indices: Sequence[int],
) -> dict[str, Any]:
    if phase not in _CONTROLLED_PHASE_ACTION_KINDS:
        raise RuntimeError("controlled_action_phase_invalid")
    if semantic_action_kind not in _CONTROLLED_ACTION_KINDS:
        raise RuntimeError("controlled_action_kind_invalid")
    if semantic_action_kind not in _CONTROLLED_PHASE_ACTION_KINDS[phase]:
        raise RuntimeError("controlled_action_phase_mismatch")
    if type(terminal_latched) is not bool:
        raise TypeError("controlled_action_terminal_latched_bool_required")
    if terminal_latched:
        raise RuntimeError("controlled_action_terminal_latched")
    if (
        not isinstance(finger_joint_indices, Sequence)
        or isinstance(finger_joint_indices, (str, bytes))
        or len(finger_joint_indices) != 2
        or len(set(finger_joint_indices)) != 2
        or any(type(index) is not int or index < 0 for index in finger_joint_indices)
    ):
        raise ValueError("controlled_action_finger_indices_invalid")

    fields = {
        name: (
            action.get(name)
            if isinstance(action, Mapping)
            else getattr(action, name, None)
        )
        for name in _ACTION_FIELDS
    }
    positions = _controlled_action_vector(
        fields["joint_positions"], allow_none=True
    )
    if fields["joint_efforts"] is not None:
        raise RuntimeError("controlled_action_channel_invalid")

    finger_kind = semantic_action_kind.startswith("GRIPPER_")
    indices = fields["joint_indices"]
    if finger_kind:
        if (
            indices is not None
            or fields["joint_velocities"] is not None
            or len(positions) <= max(finger_joint_indices)
            or any(positions[index] is None for index in finger_joint_indices)
            or any(
                value is not None and index not in finger_joint_indices
                for index, value in enumerate(positions)
            )
        ):
            raise RuntimeError("controlled_action_channel_invalid")
        channel = "finger"
        finger_targets = [
            float(positions[index]) for index in finger_joint_indices
        ]
    else:
        arm_joint_count = min(finger_joint_indices)
        velocities = (
            None
            if fields["joint_velocities"] is None
            else _controlled_action_vector(
                fields["joint_velocities"], allow_none=True
            )
        )
        if indices is not None:
            raw_indices = _controlled_action_vector(indices, allow_none=False)
            normalized_indices = []
            for index in raw_indices:
                if not isinstance(index, (int, np.integer)):
                    raise RuntimeError("controlled_action_channel_invalid")
                normalized_indices.append(int(index))
            if (
                normalized_indices != list(range(arm_joint_count))
                or len(normalized_indices) != len(positions)
                or any(value is None for value in positions)
                or velocities is not None
                and (
                    len(velocities) != len(positions)
                    or any(value is None for value in velocities)
                )
            ):
                raise RuntimeError("controlled_action_channel_invalid")
        else:
            if len(positions) != arm_joint_count or any(
                value is None for value in positions
            ):
                raise RuntimeError("controlled_action_channel_invalid")
            if velocities is not None and (
                len(velocities) != arm_joint_count
                or any(value is None for value in velocities)
            ):
                raise RuntimeError("controlled_action_channel_invalid")
        channel = "arm"
        finger_targets = None

    action_sha256 = canonical_action_sha256(action)
    return {
        "phase": phase,
        "semantic_action_kind": semantic_action_kind,
        "channel": channel,
        "finger_joint_targets": finger_targets,
        "action_sha256": action_sha256,
    }


def _controlled_index(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"controlled_action_{field}_invalid")
    result = int(value)
    if result < 0:
        raise ValueError(f"controlled_action_{field}_invalid")
    return result


def validate_controlled_action_proposal(
    *,
    action: Any,
    phase: str,
    semantic_action_kind: str,
    terminal_latched: bool,
    finger_joint_indices: Sequence[int],
    target_token: Mapping[str, Any],
    control_index: int,
    interval_index: int,
    controller_phase: str | None = None,
) -> dict[str, Any]:
    validation = _controlled_action_validation(
        action=action,
        phase=phase,
        semantic_action_kind=semantic_action_kind,
        terminal_latched=terminal_latched,
        finger_joint_indices=finger_joint_indices,
    )
    token = validate_target_token(target_token)
    expected_token_kind = "finger_joints" if validation["channel"] == "finger" else "arm_pose"
    if token["kind"] != expected_token_kind:
        raise RuntimeError("controlled_action_target_channel_mismatch")
    if validation["channel"] == "finger" and token.get("joint_indices") != list(
        finger_joint_indices
    ):
        raise RuntimeError("controlled_action_target_channel_mismatch")
    if validation["channel"] == "finger":
        descriptor = token.get("arrays", {}).get("joint_targets")
        expected_bytes = np.ascontiguousarray(
            validation["finger_joint_targets"], dtype=np.dtype("<f8")
        ).tobytes(order="C").hex()
        if (
            not isinstance(descriptor, Mapping)
            or descriptor.get("dtype") != "<f8"
            or descriptor.get("shape") != [2]
            or descriptor.get("bytes_hex") != expected_bytes
        ):
            raise RuntimeError("controlled_action_target_value_mismatch")
    control = _controlled_index(control_index, field="control_index")
    interval = _controlled_index(interval_index, field="interval_index")
    if controller_phase is None:
        controller_phase = phase
    if not isinstance(controller_phase, str) or not controller_phase:
        raise ValueError("controlled_action_controller_phase_invalid")
    payload = {
        "authority": "controlled_action_proposal_v1",
        **validation,
        "target_token": token,
        "target_token_sha256": token["sha256"],
        "control_index": control,
        "interval_index": interval,
        "controller_phase": controller_phase,
        "validated_before_commit": True,
        "terminal_latched_before_validation": False,
        "physics_steps_under_prohibited_action": 0,
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


def apply_controlled_action(
    *,
    action: Any,
    apply_action: Callable[[Any], Any],
    proposal: Mapping[str, Any] | None = None,
    commit_record: Mapping[str, Any] | None = None,
    phase: str | None = None,
    semantic_action_kind: str | None = None,
    terminal_latched: bool | None = None,
    finger_joint_indices: Sequence[int] | None = None,
) -> dict[str, Any]:
    if not callable(apply_action):
        raise TypeError("controlled_action_apply_callable_required")

    # Keep the existing direct gate available while callers migrate to the
    # explicit validate/commit/apply/receipt transaction.
    if proposal is None and commit_record is None:
        validation = _controlled_action_validation(
            action=action,
            phase=phase,
            semantic_action_kind=semantic_action_kind,
            terminal_latched=terminal_latched,
            finger_joint_indices=finger_joint_indices,
        )
        payload = {
            "authority": "controlled_phase_action_preapply_v1",
            **validation,
            "validated_before_apply": True,
            "terminal_latched_before_apply": False,
            "physics_steps_under_prohibited_action": 0,
        }
        apply_action(action)
        return {**payload, "applied": True}

    if proposal is None or commit_record is None:
        raise ValueError("controlled_action_transaction_incomplete")
    if not isinstance(proposal, Mapping) or not isinstance(commit_record, Mapping):
        raise TypeError("controlled_action_transaction_mapping_required")
    proposal = copy.deepcopy(dict(proposal))
    commit = copy.deepcopy(dict(commit_record))
    proposal_sha256 = proposal.pop("sha256", None)
    commit_sha256 = commit.pop("sha256", None)
    if (
        proposal.get("authority") != "controlled_action_proposal_v1"
        or proposal_sha256 != canonical_json_sha256(proposal)
    ):
        raise RuntimeError("controlled_action_proposal_invalid")
    if commit.get("authority") != "controlled_action_commit_v1":
        raise RuntimeError("controlled_action_commit_invalid")
    if (
        commit_sha256 != canonical_json_sha256(commit)
        or
        commit.get("proposal_sha256") != proposal_sha256
        or commit.get("action_sha256") != canonical_action_sha256(action)
        or commit.get("action_sha256") != proposal.get("action_sha256")
        or commit.get("target_token_sha256") != proposal.get("target_token_sha256")
        or commit.get("control_index") != proposal.get("control_index")
        or commit.get("interval_index") != proposal.get("interval_index")
        or commit.get("controller_phase") != proposal.get("controller_phase")
        or commit.get("committed") is not True
    ):
        raise RuntimeError("controlled_action_commit_mismatch")
    action_index = _controlled_index(
        commit.get("action_index"), field="action_index"
    )
    apply_action(action)
    receipt = {
        "authority": "controlled_action_applied_receipt_v1",
        "phase": proposal["phase"],
        "semantic_action_kind": proposal["semantic_action_kind"],
        "channel": proposal["channel"],
        "action_sha256": proposal["action_sha256"],
        "target_token": copy.deepcopy(proposal["target_token"]),
        "target_token_sha256": proposal["target_token_sha256"],
        "proposal_sha256": proposal_sha256,
        "commit_sha256": commit_sha256,
        "control_index": proposal["control_index"],
        "action_index": action_index,
        "apply_index": action_index,
        "interval_index": proposal["interval_index"],
        "controller_phase": proposal["controller_phase"],
        "applied": True,
        "normal_api_return": True,
        "physics_steps_before_receipt": 0,
    }
    return {**receipt, "sha256": canonical_json_sha256(receipt)}


def execute_controlled_action_transaction(
    *,
    fluid_loop: Any,
    action: Any,
    read_action_context: Callable[[], Mapping[str, Any]],
    apply_action: Callable[[Any], Any],
    log_action: Callable[[Any], Any] | None = None,
) -> dict[str, Any] | None:
    stage = "action_context"
    context = None
    proposal = None
    commit = None
    candidate_receipt = None
    apply_callback_entered = False
    apply_callback_normal_return = False

    def tracked_apply(value: Any) -> None:
        nonlocal apply_callback_entered, apply_callback_normal_return
        apply_callback_entered = True
        apply_action(value)
        apply_callback_normal_return = True

    try:
        if not callable(read_action_context):
            raise TypeError("controlled_action_context_callable_required")
        if not callable(apply_action):
            raise TypeError("controlled_action_apply_callable_required")
        if log_action is not None and not callable(log_action):
            raise TypeError("controlled_action_logger_callable_required")
        context = read_action_context()
        if not isinstance(context, Mapping):
            raise TypeError("controlled_action_context_mapping_required")
        context = copy.deepcopy(dict(context))

        stage = "proposal_validation"
        proposal = validate_controlled_action_proposal(
            action=action,
            phase=context["phase"],
            semantic_action_kind=context["semantic_action_kind"],
            terminal_latched=context["terminal_latched"],
            finger_joint_indices=context["finger_joint_indices"],
            target_token=context["target_token"],
            control_index=context["control_index"],
            interval_index=fluid_loop.next_controlled_interval_index,
            controller_phase=context.get("controller_phase"),
        )
        action_for_log = copy.deepcopy(action)
        if not fluid_loop.validate_controlled_action_phase(
            context["phase"],
            proposal=proposal,
        ):
            return None

        stage = "commit"
        commit = fluid_loop.commit_controlled_action(action, proposal)

        stage = "apply"
        candidate_receipt = apply_controlled_action(
            action=action,
            proposal=proposal,
            commit_record=commit,
            apply_action=tracked_apply,
        )

        stage = "receipt_integrity"
        if candidate_receipt["action_sha256"] != commit["action_sha256"]:
            raise RuntimeError("controlled_contact_preapply_action_hash_mismatch")

        stage = "receipt_confirmation"
        fluid_loop.confirm_controlled_action_applied(candidate_receipt)

        stage = "action_logging"
        if log_action is not None:
            log_action(action_for_log)
    except Exception as exc:
        receipt_confirmed = bool(
            getattr(fluid_loop, "_pending_controlled_receipt", None) is not None
        )
        if receipt_confirmed:
            application_outcome = "confirmed_applied"
        elif apply_callback_normal_return:
            application_outcome = "normal_return_unconfirmed"
        elif apply_callback_entered:
            application_outcome = "invoked_outcome_unknown"
        else:
            application_outcome = "not_invoked"
        fluid_loop.queue_controlled_prephysics_failure(
            stage=stage,
            error=exc,
            application_outcome=application_outcome,
            apply_callback_entered=apply_callback_entered,
            apply_callback_normal_return=apply_callback_normal_return,
            proposal=proposal,
            commit_record=commit,
            candidate_receipt=candidate_receipt,
        )
        return None

    return {
        "action_context": context,
        "proposal": proposal,
        "commit_record": commit,
        "applied_receipt": candidate_receipt,
        "action_sha256": commit["action_sha256"],
    }


def current_fluid_run_id() -> str:
    """Return the identity shared by every fluid attempt in this process."""
    return _PROCESS_RUN_ID


def prepare_fluid_evidence_directory(path: str | Path) -> Path:
    """Claim an empty evidence directory for this process or fail closed."""
    output_path = Path(path)
    if output_path.exists() and not output_path.is_dir():
        raise RuntimeError(f"fluid_evidence_path_not_directory:{output_path}")
    if not output_path.exists():
        try:
            output_path.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            if not output_path.is_dir():
                raise RuntimeError(
                    f"fluid_evidence_path_not_directory:{output_path}"
                ) from None
    if any(output_path.iterdir()):
        raise RuntimeError(f"fluid_evidence_directory_not_empty:{output_path}")

    owner_path = output_path / ".fluid-evidence-owner.json"
    owner = json.dumps(
        {"run_id": current_fluid_run_id(), "pid": os.getpid()},
        sort_keys=True,
        separators=(",", ":"),
    )
    try:
        with owner_path.open("x", encoding="utf-8") as stream:
            stream.write(owner)
            stream.write("\n")
    except FileExistsError:
        raise RuntimeError(
            f"fluid_evidence_directory_not_empty:{output_path}"
        ) from None
    if any(entry != owner_path for entry in output_path.iterdir()):
        raise RuntimeError(f"fluid_evidence_directory_not_empty:{output_path}")
    return output_path


def _required_evidence_string(value: Mapping[str, Any], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result:
        raise ValueError(f"fluid_evidence_{field}_invalid")
    return result


def _required_evidence_index(value: Mapping[str, Any], field: str) -> int:
    result = value.get(field)
    if isinstance(result, bool) or not isinstance(result, (int, np.integer)):
        raise ValueError(f"fluid_evidence_{field}_invalid")
    result = int(result)
    if result < 0:
        raise ValueError(f"fluid_evidence_{field}_invalid")
    return result


def _observation_evidence_keys(payload: Mapping[str, Any]) -> set[tuple[Any, ...]]:
    record = payload.get("record")
    if not isinstance(record, Mapping):
        raise ValueError("fluid_observation_record_mapping_required")
    run_id = _required_evidence_string(record, "run_id")
    attempt_id = _required_evidence_string(record, "attempt_id")
    episode_id = _required_evidence_string(record, "episode_id")
    sample_index = _required_evidence_index(record, "sample_index")
    observation_index = _required_evidence_index(record, "observation_index")
    if record.get("attempt_status") != "active":
        raise ValueError("fluid_evidence_attempt_status_invalid")
    if not isinstance(record.get("cumulative_containment"), Mapping):
        raise ValueError("fluid_evidence_cumulative_containment_mapping_required")
    return {
        ("sample", run_id, sample_index),
        ("observation", run_id, attempt_id, episode_id, observation_index),
    }


def _episode_evidence_keys(payload: Mapping[str, Any]) -> set[tuple[Any, ...]]:
    run_id = _required_evidence_string(payload, "run_id")
    attempt_id = _required_evidence_string(payload, "attempt_id")
    _required_evidence_string(payload, "episode_id")
    status = payload.get("attempt_status")
    if status not in _ATTEMPT_STATUSES:
        raise ValueError("fluid_evidence_attempt_status_invalid")
    if not isinstance(payload.get("cumulative_containment"), Mapping):
        raise ValueError("fluid_evidence_cumulative_containment_mapping_required")
    return {("attempt", run_id, attempt_id)}


def _file_signature(stream: Any) -> tuple[int, int, int]:
    stat = os.fstat(stream.fileno())
    return (int(stat.st_ino), int(stat.st_size), int(stat.st_mtime_ns))


def _append_evidence_jsonl(
    path: str | Path,
    payload: Mapping[str, Any],
    *,
    ledger_name: str,
    key_reader: Callable[[Mapping[str, Any]], set[tuple[Any, ...]]],
) -> None:
    new_keys = key_reader(payload)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cache_key = (ledger_name, output_path.resolve())
    with output_path.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            signature = _file_signature(stream)
            cached = _EVIDENCE_LEDGER_CACHE.get(cache_key)
            if cached is not None and cached[0] == signature:
                existing_keys = set(cached[1])
            else:
                existing_keys: set[tuple[Any, ...]] = set()
                stream.seek(0)
                for line_number, line in enumerate(stream, start=1):
                    if not line.endswith("\n") or not line.strip():
                        raise RuntimeError(
                            "fluid_evidence_jsonl_invalid:"
                            f"{output_path}:line={line_number}"
                        )
                    try:
                        existing_payload = json.loads(line)
                        if not isinstance(existing_payload, Mapping):
                            raise ValueError("payload_mapping_required")
                        record_keys = key_reader(existing_payload)
                    except (TypeError, ValueError, json.JSONDecodeError) as exc:
                        raise RuntimeError(
                            "fluid_evidence_jsonl_invalid:"
                            f"{output_path}:line={line_number}"
                        ) from exc
                    duplicate = existing_keys.intersection(record_keys)
                    if duplicate:
                        raise RuntimeError(
                            "fluid_evidence_duplicate_existing:"
                            f"{output_path}:{sorted(map(repr, duplicate))}"
                        )
                    existing_keys.update(record_keys)
                _EVIDENCE_LEDGER_CACHE[cache_key] = (signature, existing_keys)

            duplicate = existing_keys.intersection(new_keys)
            if duplicate:
                raise RuntimeError(
                    "fluid_evidence_duplicate:"
                    f"{output_path}:{sorted(map(repr, duplicate))}"
                )
            stream.seek(0, os.SEEK_END)
            stream.write(encoded)
            stream.write("\n")
            stream.flush()
            existing_keys.update(new_keys)
            _EVIDENCE_LEDGER_CACHE[cache_key] = (
                _file_signature(stream),
                existing_keys,
            )
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def append_fluid_observation_evidence(
    path: str | Path,
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    """Append the compact provenance for one exact model-facing observation."""
    if not isinstance(observation, Mapping):
        raise TypeError("fluid_observation_mapping_required")
    payload: dict[str, Any] = {}
    for key in ("record", "score", "attachment"):
        value = observation.get(key)
        if not isinstance(value, Mapping):
            raise ValueError(f"fluid_observation_{key}_mapping_required")
        payload[key] = dict(value)
    _append_evidence_jsonl(
        path,
        payload,
        ledger_name="observation",
        key_reader=_observation_evidence_keys,
    )
    return payload


def append_fluid_episode_evidence(
    path: str | Path,
    evaluation: Mapping[str, Any],
) -> dict[str, Any]:
    """Append one terminal episode evaluation for collect or infer mode."""
    if not isinstance(evaluation, Mapping):
        raise TypeError("fluid_episode_evaluation_mapping_required")
    payload = dict(evaluation)
    _append_evidence_jsonl(
        path,
        payload,
        ledger_name="episode",
        key_reader=_episode_evidence_keys,
    )
    return payload


def observation_limit_reached(
    completed_observations: int,
    maximum_observations: int | None,
) -> bool:
    if type(completed_observations) is not int or completed_observations < 0:
        raise ValueError("completed_observations_invalid")
    if maximum_observations is None:
        return False
    if type(maximum_observations) is not int or maximum_observations <= 0:
        raise ValueError("maximum_observations_invalid")
    return completed_observations >= maximum_observations


def attempt_limit_reached(completed_attempts: int, maximum_attempts: int) -> bool:
    if type(completed_attempts) is not int or completed_attempts < 0:
        raise ValueError("completed_attempts_invalid")
    if type(maximum_attempts) is not int or maximum_attempts <= 0:
        raise ValueError("maximum_attempts_invalid")
    return completed_attempts >= maximum_attempts


def online_fluid_run_complete(
    *,
    mode: str,
    completed_attempts: int,
    accepted_episodes: int,
    maximum_episodes: int,
    maximum_attempts: int,
) -> bool:
    if mode not in {"collect", "infer"}:
        raise ValueError("online_fluid_mode_invalid")
    if type(accepted_episodes) is not int or accepted_episodes < 0:
        raise ValueError("accepted_episodes_invalid")
    if type(maximum_episodes) is not int or maximum_episodes <= 0:
        raise ValueError("maximum_episodes_invalid")
    if attempt_limit_reached(completed_attempts, maximum_attempts):
        return True
    completed_episodes = (
        accepted_episodes if mode == "collect" else completed_attempts
    )
    return completed_episodes >= maximum_episodes


def observation_limit_failure_reason(
    *,
    per_episode_limit_hit: bool,
    global_limit_hit: bool,
) -> str | None:
    if type(per_episode_limit_hit) is not bool or type(global_limit_hit) is not bool:
        raise TypeError("observation_limit_flags_bool_required")
    if per_episode_limit_hit:
        return "max_observations_per_episode_reached"
    if global_limit_hit:
        return "max_fluid_observations_reached"
    return None


def observation_limit_termination_reason(
    *,
    controller_done: bool,
    per_episode_limit_hit: bool,
    global_limit_hit: bool,
) -> str | None:
    if type(controller_done) is not bool:
        raise TypeError("controller_done_bool_required")
    boundary_reason = observation_limit_failure_reason(
        per_episode_limit_hit=per_episode_limit_hit,
        global_limit_hit=global_limit_hit,
    )
    return None if controller_done else boundary_reason


def contact_acquisition_probe_control_contract(
    *,
    controller_evidence: Mapping[str, Any] | None,
    attachment_evidence: Mapping[str, Any] | None,
    expected_source_ownership: str | None,
    controller_completed: bool,
    terminal_phase: str | None,
    terminal_action: Any,
    pour_started: bool,
    cumulative_containment_valid: bool,
    source_visual_sync_valid: bool,
) -> dict[str, Any]:
    """Return the fail-closed terminal contract for a contact-only probe."""
    control = (
        controller_evidence
        if isinstance(controller_evidence, Mapping)
        else {}
    )
    attachment = (
        attachment_evidence
        if isinstance(attachment_evidence, Mapping)
        else {}
    )
    profile = control.get("expert_control_profile")
    profile_key = {
        "native_expert_v1": "native_pick",
        "contact_pick_v1": "contact_pick",
    }.get(profile)
    profile_evidence = (
        control.get(profile_key) if profile_key is not None else None
    )
    profile_control = (
        profile_evidence if isinstance(profile_evidence, Mapping) else {}
    )
    phase_history = profile_control.get("phase_history")
    contact_phase_history_valid = bool(
        isinstance(phase_history, Sequence)
        and not isinstance(phase_history, (str, bytes, bytearray))
        and phase_history
    )
    contact_phase_history = (
        tuple(phase_history)
        if contact_phase_history_valid
        else ()
    )
    if profile == "native_expert_v1":
        controller_lift_not_emitted = bool(
            profile_control.get("lift_command_emitted") is False
            and profile_control.get("last_emitted_event") == 4
        )
        profile_terminal_identity = (
            profile_control.get("last_emitted_event") == 4
        )
    elif profile == "contact_pick_v1":
        controller_lift_not_emitted = bool(
            contact_phase_history_valid
            and "LIFT" not in contact_phase_history
            and "HOLD" not in contact_phase_history
        )
        profile_terminal_identity = bool(
            profile_control.get("phase") == "CONTACT_SETTLE"
            and profile_control.get("probe_completed") is True
            and contact_phase_history_valid
            and contact_phase_history[-1] == "CONTACT_SETTLE"
        )
    else:
        controller_lift_not_emitted = False
        profile_terminal_identity = False
    other_profile_key = (
        "contact_pick" if profile_key == "native_pick" else "native_pick"
    )
    writer_audit = attachment.get("source_writer_audit")
    writer_audit = writer_audit if isinstance(writer_audit, Mapping) else {}
    pour_forward_invocation_count = control.get(
        "pour_forward_invocation_count"
    )
    pour_not_invoked = bool(
        type(pour_forward_invocation_count) is int
        and pour_forward_invocation_count == 0
    )
    writer_call_count = writer_audit.get("call_count")
    kinematic_target_update_count = attachment.get(
        "kinematic_target_update_count"
    )

    checks = {
        "controller_completed": (
            controller_completed is True
            or (
                control.get("execution_mode") == "close_contact_allowed_v1"
                and profile_terminal_identity
                and controller_lift_not_emitted
            )
        ),
        "collect_mode": control.get("mode") == "collect",
        "dynamic_source_ownership": (
            expected_source_ownership == "contact_friction_dynamic_v1"
            and control.get("source_ownership")
            == "contact_friction_dynamic_v1"
        ),
        "probe_execution_mode": (
            control.get("execution_mode")
            in {
                "contact_acquisition_probe_v1",
                "close_contact_allowed_v1",
            }
            and control.get("contact_acquisition_probe") is True
            and control.get("contact_grasp_required") is True
        ),
        "supported_control_profile": (
            profile in _CONTACT_ACQUISITION_PROBE_PROFILES
            and isinstance(profile_evidence, Mapping)
            and other_profile_key in control
            and control.get(other_profile_key) is None
        ),
        "profile_terminal_identity": profile_terminal_identity,
        "controller_close_command_emitted": (
            profile_control.get("close_command_emitted") is True
        ),
        "attachment_close_command_observed": (
            attachment.get("close_command_observed") is True
        ),
        "controller_lift_command_not_emitted": controller_lift_not_emitted,
        "attachment_lift_command_not_observed": (
            attachment.get("lift_command_observed") is False
        ),
        "probe_qualified_now": (
            attachment.get("probe_qualified_now") is True
            or (
                control.get("execution_mode") == "close_contact_allowed_v1"
                and attachment.get("close_command_observed") is True
            )
        ),
        "pour_forward_not_called": pour_not_invoked,
        "pour_action_not_emitted": pour_not_invoked,
        "terminal_outer_finished": terminal_phase == "FINISHED",
        "terminal_action_is_none": terminal_action is None,
        "dynamic_attachment_mode": (
            attachment.get("mode") == "contact_friction_dynamic_v1"
            and attachment.get("source_dynamic") is True
        ),
        "source_non_kinematic": (
            type(kinematic_target_update_count) is int
            and kinematic_target_update_count == 0
        ),
        "mechanical_attachment_not_used": (
            attachment.get("mechanical_attachment_used") is False
        ),
        "attachment_failure_free": (
            "failure_reason" in attachment
            and attachment.get("failure_reason") is None
        ),
        "source_writer_audit_valid": (
            writer_audit.get("coverage_complete") is True
            and writer_audit.get("valid") is True
        ),
        "source_writer_audit_zero": (
            type(writer_call_count) is int
            and writer_call_count == 0
        ),
        "pour_not_started": pour_started is False,
        "cumulative_containment_valid": cumulative_containment_valid is True,
        "source_visual_sync_valid": source_visual_sync_valid is True,
    }
    return {
        "id": _CONTACT_ACQUISITION_PROBE_CONTROL_CONTRACT_ID,
        "schema_version": _CONTACT_ACQUISITION_PROBE_CONTROL_CONTRACT_VERSION,
        "supported_control_profiles": list(
            _CONTACT_ACQUISITION_PROBE_PROFILES
        ),
        "selected_control_profile": (
            profile if isinstance(profile, str) else None
        ),
        "checks": checks,
        "valid": all(checks.values()),
    }


def initialize_controller_after_task_reset(
    task: Any,
    controller_factory: Callable[[], Any],
) -> Any:
    task.reset()
    return controller_factory()


def reset_task_then_controller(task: Any, controller: Any) -> None:
    task.reset()
    controller.reset()


def observation_video_fps(rendering_dt: float) -> float:
    if (
        isinstance(rendering_dt, bool)
        or not isinstance(rendering_dt, (int, float, np.number))
        or not math.isfinite(float(rendering_dt))
        or float(rendering_dt) <= 0.0
    ):
        raise ValueError("rendering_dt_invalid")
    frames_per_second = 1.0 / float(rendering_dt)
    rounded = float(round(frames_per_second))
    return rounded if math.isclose(frames_per_second, rounded, abs_tol=1.0e-10) else frames_per_second


def fluid_control_dt(
    *,
    physics_dt: float,
    physics_substeps_per_observation: int,
    rendering_dt: float,
) -> float:
    for name, value in (
        ("physics_dt", physics_dt),
        ("rendering_dt", rendering_dt),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float, np.number))
            or not math.isfinite(float(value))
            or float(value) <= 0.0
        ):
            raise ValueError(f"fluid_control_{name}_invalid")
    if (
        type(physics_substeps_per_observation) is not int
        or physics_substeps_per_observation <= 0
    ):
        raise ValueError("fluid_control_substeps_invalid")
    result = float(physics_dt) * physics_substeps_per_observation
    if not math.isclose(
        result,
        float(rendering_dt),
        rel_tol=0.0,
        abs_tol=1.0e-12,
    ):
        raise ValueError(
            "fluid_control_dt_rendering_mismatch:"
            f"control={result}:rendering={float(rendering_dt)}"
        )
    return result


def model_camera_video_rgb(
    state: Mapping[str, Any],
    *,
    camera_keys: Sequence[str],
    expected_shape: Sequence[int],
) -> np.ndarray:
    if not isinstance(state, Mapping):
        raise ValueError("task_state_mapping_required")
    camera_data = state.get("camera_data")
    if not isinstance(camera_data, Mapping):
        raise ValueError("model_camera_data_mapping_required")
    keys = tuple(camera_keys)
    shape = tuple(int(value) for value in expected_shape)
    if set(camera_data) != set(keys):
        raise ValueError("model_camera_keys_mismatch")
    frames = []
    for key in keys:
        array = np.asarray(camera_data[key])
        if array.shape != shape:
            raise ValueError(f"model_camera_shape_mismatch:{key}")
        if array.dtype != np.uint8:
            raise ValueError(f"model_camera_dtype_mismatch:{key}")
        frames.append(np.transpose(array, (1, 2, 0)))
    return np.ascontiguousarray(np.concatenate(frames, axis=1))


class _NullAttachment:
    def reset(self) -> None:
        return None

    def maybe_attach(self, controller: Any, state: Mapping[str, Any]) -> bool:
        del controller, state
        return False

    def update_before_substep(self) -> None:
        return None

    def update_after_substep(self) -> None:
        return None

    def record(self) -> dict[str, Any]:
        return {"mode": "none", "attached": False}


class FluidEvaluationLoop:
    """Own one action-to-observation transition in the fluid evaluation mode."""

    def __init__(
        self,
        *,
        world: Any,
        task: Any,
        expected_particle_count: int,
        physics_substeps_per_observation: int,
        physics_substep_dt: float,
        read_particles: Callable[[], Any],
        score_particles: Callable[[np.ndarray], Mapping[str, Any]],
        reconstruct: Callable[[np.ndarray], Mapping[str, Any]],
        author_surface: Callable[[Mapping[str, Any], SurfaceFrameToken], Mapping[str, Any]],
        invalidate_surface: Callable[[str], None],
        expected_camera_keys: Sequence[str],
        expected_camera_shape: Sequence[int],
        camera_contract: Mapping[str, Any],
        attachment: Any | None = None,
        adapt_state: Callable[[Mapping[str, Any]], Any] | None = None,
        sync_source_visual_state: Callable[[], Mapping[str, Any]] | None = None,
        initial_render_warmup_updates: int = 0,
        reset_pre_roll_substeps: int = 0,
        sample_containment_after_substep: (
            Callable[[], Mapping[str, Any] | None] | None
        ) = None,
        expected_source_ownership: str | None = None,
        controlled_contact_interlock: bool = False,
        run_id: str | None = None,
    ) -> None:
        if type(expected_particle_count) is not int or expected_particle_count <= 0:
            raise ValueError("expected_particle_count_invalid")
        if (
            type(physics_substeps_per_observation) is not int
            or physics_substeps_per_observation <= 0
        ):
            raise ValueError("physics_substeps_per_observation_invalid")
        if not math.isfinite(physics_substep_dt) or physics_substep_dt <= 0.0:
            raise ValueError("physics_substep_dt_invalid")
        if (
            type(initial_render_warmup_updates) is not int
            or initial_render_warmup_updates < 0
        ):
            raise ValueError("initial_render_warmup_updates_invalid")
        if type(reset_pre_roll_substeps) is not int or reset_pre_roll_substeps < 0:
            raise ValueError("reset_pre_roll_substeps_invalid")
        camera_keys = tuple(expected_camera_keys)
        if not camera_keys or len(camera_keys) != len(set(camera_keys)):
            raise ValueError("expected_camera_keys_invalid")
        camera_shape = tuple(int(value) for value in expected_camera_shape)
        if len(camera_shape) != 3 or any(value <= 0 for value in camera_shape):
            raise ValueError("expected_camera_shape_invalid")
        if not isinstance(camera_contract, Mapping):
            raise ValueError("camera_contract_mapping_required")
        camera_contract_id = camera_contract.get("id")
        camera_contract_sha256 = camera_contract.get("sha256")
        if not isinstance(camera_contract_id, str) or not camera_contract_id:
            raise ValueError("camera_contract_id_invalid")
        if (
            not isinstance(camera_contract_sha256, str)
            or len(camera_contract_sha256) != 64
            or any(character not in "0123456789abcdef" for character in camera_contract_sha256)
        ):
            raise ValueError("camera_contract_sha256_invalid")
        if not hasattr(world, "step") or not hasattr(world, "render"):
            raise TypeError("world_step_and_render_required")
        if not hasattr(task, "step"):
            raise TypeError("task_step_required")
        if sync_source_visual_state is not None and not callable(
            sync_source_visual_state
        ):
            raise TypeError("source_visual_sync_callable_required")
        if sample_containment_after_substep is not None and not callable(
            sample_containment_after_substep
        ):
            raise TypeError("substep_containment_callback_callable_required")
        if run_id is not None and (not isinstance(run_id, str) or not run_id):
            raise ValueError("run_id_invalid")
        if type(controlled_contact_interlock) is not bool:
            raise TypeError("controlled_contact_interlock_bool_required")
        if controlled_contact_interlock and (
            not callable(getattr(world, "play", None))
            or not callable(getattr(world, "pause", None))
            or not callable(getattr(world, "is_playing", None))
        ):
            raise TypeError("controlled_contact_world_timeline_api_required")
        if expected_source_ownership is not None and expected_source_ownership not in (
            "gripper_attached_kinematic_vessel",
            "contact_friction_dynamic_v1",
        ):
            raise ValueError("expected_source_ownership_unsupported")

        self.world = world
        self.task = task
        self.expected_particle_count = expected_particle_count
        self.physics_substeps_per_observation = physics_substeps_per_observation
        self.physics_substep_dt = float(physics_substep_dt)
        self.initial_render_warmup_updates = initial_render_warmup_updates
        self.reset_pre_roll_substeps = reset_pre_roll_substeps
        self.read_particles = read_particles
        self.score_particles = score_particles
        self.expected_camera_keys = camera_keys
        self.expected_camera_shape = camera_shape
        self.camera_contract = copy.deepcopy(dict(camera_contract))
        self.camera_contract_identity = {
            "id": camera_contract_id,
            "sha256": camera_contract_sha256,
        }
        self.attachment = attachment if attachment is not None else _NullAttachment()
        self.adapt_state = adapt_state
        self.sync_source_visual_state = sync_source_visual_state
        self.sample_containment_after_substep = sample_containment_after_substep
        self.expected_source_ownership = expected_source_ownership
        self.controlled_contact_interlock = controlled_contact_interlock
        self.run_id = run_id or current_fluid_run_id()

        self._episode_id: str | None = None
        self._attempt_id: str | None = None
        self._attempt_status: str | None = None
        self._attempt_sealed = False
        self._automatically_sealed_attempts: list[dict[str, Any]] = []
        self._observation_index = 0
        self._logical_steps = 0
        self._integration_steps = 0
        self._pending_action: object | Any = _NO_PENDING_ACTION
        self._pending_action_sha256: str | None = None
        self._next_controlled_action_index = 0
        self._pending_controlled_commit: dict[str, Any] | None = None
        self._pending_controlled_receipt: dict[str, Any] | None = None
        self._active_precontact_lease: dict[str, Any] | None = None
        self._required_next_precontact_target_sha256: str | None = None
        self._pending_controlled_terminal: dict[str, Any] | None = None
        self._pending_controlled_terminal_before: tuple[int, float] | None = None
        self._pending_controlled_terminal_variant: str | None = None
        self._authority_origin: tuple[int, float] | None = None
        self._last_authority: tuple[int, float] | None = None
        self._last_state: Mapping[str, Any] | None = None
        self._last_score: dict[str, Any] | None = None
        self._last_source_visual_sync: dict[str, Any] | None = None
        self._source_visual_sync_all_valid = True
        self._failed = False
        self._render_index = 0
        self._pour_started = False
        self._expected_substep_samples = 0
        self._cumulative_containment = self._empty_containment_summary()

        self._surface_runtime = OnlineFluidSurfaceRuntime(
            expected_particle_count=expected_particle_count,
            physics_substeps_per_observation=physics_substeps_per_observation,
            physics_substep_dt=physics_substep_dt,
            reconstruct=reconstruct,
            author_surface=author_surface,
            invalidate_surface=invalidate_surface,
            render_surface=self._render_surface,
            capture_cameras=self._capture_model_cameras,
        )

    @staticmethod
    def _read_world_value(world: Any, name: str) -> Any:
        value = getattr(world, name, None)
        return value() if callable(value) else value

    def _authority_snapshot(self) -> tuple[int, float]:
        step = self._read_world_value(self.world, "current_time_step_index")
        current_time = self._read_world_value(self.world, "current_time")
        if isinstance(step, bool) or not isinstance(step, (int, np.integer)):
            raise RuntimeError("world_step_counter_unavailable")
        if not isinstance(current_time, (int, float, np.number)):
            raise RuntimeError("world_time_unavailable")
        result = (int(step), float(current_time))
        if result[0] < 0 or not math.isfinite(result[1]) or result[1] < 0.0:
            raise RuntimeError("world_authority_invalid")
        return result

    def _controlled_world_step(self) -> None:
        before = self._authority_snapshot()
        if self.world.is_playing():
            raise RuntimeError("controlled_contact_world_not_paused_before_step")
        try:
            self.world.play()
            after_play = self._authority_snapshot()
            if after_play != before or not self.world.is_playing():
                raise RuntimeError("controlled_contact_play_advanced_physics")
            self.world.step(render=False)
        finally:
            pause_error = None
            try:
                self.world.pause()
            except Exception as exc:
                pause_error = exc
                if self.world.is_playing():
                    try:
                        self.world.pause()
                    except Exception:
                        pass
            if self.world.is_playing():
                raise RuntimeError("controlled_contact_pause_failed") from pause_error
            if pause_error is not None:
                raise RuntimeError("controlled_contact_pause_failed") from pause_error
        after_pause = self._authority_snapshot()
        expected = (before[0] + 1, before[1] + self.physics_substep_dt)
        if (
            after_pause[0] != expected[0]
            or not math.isclose(
                after_pause[1], expected[1], rel_tol=0.0, abs_tol=1.0e-8
            )
        ):
            raise RuntimeError("controlled_contact_step_delta_invalid")

    def _pause_controlled_timeline(self) -> None:
        if not self.controlled_contact_interlock:
            return
        before = self._authority_snapshot()
        if self.world.is_playing():
            self.world.pause()
        after = self._authority_snapshot()
        if after != before:
            raise RuntimeError("controlled_contact_pause_advanced_physics")
        if self.world.is_playing():
            raise RuntimeError("controlled_contact_pause_failed")

    @property
    def attempt_id(self) -> str | None:
        return self._attempt_id

    @property
    def attempt_sealed(self) -> bool:
        return self._attempt_sealed

    @property
    def ready_for_action(self) -> bool:
        return bool(
            self._episode_id is not None
            and not self._attempt_sealed
            and not self._failed
            and self._pending_controlled_terminal is None
            and self._observation_index > 0
            and self._pending_action is _NO_PENDING_ACTION
        )

    @property
    def controlled_loop_active(self) -> bool:
        return bool(
            self.controlled_contact_interlock
            and self._episode_id is not None
            and not self._attempt_sealed
            and not self._failed
        )

    @property
    def controlled_terminal_pending(self) -> bool:
        return self._pending_controlled_terminal is not None

    @property
    def controlled_interval_pending(self) -> bool:
        return bool(
            self.controlled_contact_interlock
            and self._pending_action is not _NO_PENDING_ACTION
        )

    @property
    def mechanical_attachment_used(self) -> bool:
        record = self.attachment.record()
        if not isinstance(record, Mapping):
            raise TypeError("attachment_record_mapping_required")
        value = record.get("mechanical_attachment_used")
        if type(value) is not bool:
            raise ValueError("mechanical_attachment_used_bool_required")
        return value

    @property
    def next_controlled_interval_index(self) -> int:
        if self._episode_id is None or self._observation_index <= 0:
            raise RuntimeError("controlled_action_initial_observation_required")
        return self._observation_index - 1

    @property
    def automatically_sealed_attempts(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._automatically_sealed_attempts)

    def _empty_containment_summary(self) -> dict[str, Any]:
        return {
            "expected_particle_count": self.expected_particle_count,
            "sample_count": 0,
            "observation_sample_count": 0,
            "substep_sample_count": 0,
            "source_min": None,
            "non_source_max": {
                field: 0 for field in _NON_SOURCE_PARTITION_FIELDS
            },
            "pre_pour_source_min": None,
            "pre_pour_non_source_max": {
                field: 0 for field in _NON_SOURCE_PARTITION_FIELDS
            },
            "partition_total_min": None,
            "partition_total_max": None,
            "partition_integrity_valid": True,
            "first_spill_physics_step": None,
            "ever_spilled": False,
            "below_table_max": 0,
            "nonfinite_max": 0,
            "pour_started_physics_step": None,
        }

    @staticmethod
    def _containment_count(value: Mapping[str, Any], field: str) -> int:
        count_value = value.get(field)
        if (
            isinstance(count_value, bool)
            or not isinstance(count_value, (int, np.integer))
            or int(count_value) < 0
        ):
            raise ValueError(f"containment_{field}_invalid")
        return int(count_value)

    def _latch_pour_started(self, physics_step: int) -> None:
        if self._pour_started:
            return
        self._pour_started = True
        self._cumulative_containment["pour_started_physics_step"] = int(
            physics_step
        )

    def mark_pour_started(self) -> None:
        if self._episode_id is None:
            raise RuntimeError("episode_not_reset")
        if self._attempt_sealed:
            raise RuntimeError("attempt_sealed_requires_reset")
        if self._failed:
            raise RuntimeError("episode_runtime_failed_requires_reset")
        self._latch_pour_started(self._authority_snapshot()[0])

    def _accumulate_containment(
        self,
        value: Mapping[str, Any],
        *,
        physics_step: int,
        sample_kind: str,
    ) -> None:
        if not isinstance(value, Mapping):
            raise ValueError("containment_sample_mapping_required")
        counts = {
            field: self._containment_count(value, field)
            for field in _PARTITION_FIELDS
        }
        particle_count = self._containment_count(value, "particle_count")
        partition_complete = value.get("partition_complete")
        if type(partition_complete) is not bool:
            raise ValueError("containment_partition_complete_bool_required")
        pour_started = value.get("pour_started", False)
        if type(pour_started) is not bool:
            raise ValueError("containment_pour_started_bool_required")
        if pour_started:
            self._latch_pour_started(physics_step)

        summary = self._cumulative_containment
        summary["sample_count"] += 1
        if sample_kind == "substep":
            summary["substep_sample_count"] += 1
        elif sample_kind == "observation":
            summary["observation_sample_count"] += 1
        else:
            raise ValueError("containment_sample_kind_invalid")

        source = counts["source"]
        summary["source_min"] = (
            source
            if summary["source_min"] is None
            else min(summary["source_min"], source)
        )
        for field in _NON_SOURCE_PARTITION_FIELDS:
            summary["non_source_max"][field] = max(
                summary["non_source_max"][field], counts[field]
            )

        partition_total = sum(counts.values())
        summary["partition_total_min"] = (
            partition_total
            if summary["partition_total_min"] is None
            else min(summary["partition_total_min"], partition_total)
        )
        summary["partition_total_max"] = (
            partition_total
            if summary["partition_total_max"] is None
            else max(summary["partition_total_max"], partition_total)
        )
        summary["partition_integrity_valid"] = bool(
            summary["partition_integrity_valid"]
            and partition_complete
            and particle_count == self.expected_particle_count
            and partition_total == self.expected_particle_count
        )
        summary["below_table_max"] = max(
            summary["below_table_max"], counts["below_table"]
        )
        summary["nonfinite_max"] = max(
            summary["nonfinite_max"], counts["nonfinite"]
        )

        outside_source = source < self.expected_particle_count or any(
            counts[field] > 0 for field in _NON_SOURCE_PARTITION_FIELDS
        )
        if outside_source:
            summary["ever_spilled"] = True
            if summary["first_spill_physics_step"] is None:
                summary["first_spill_physics_step"] = int(physics_step)
        if not self._pour_started:
            summary["pre_pour_source_min"] = (
                source
                if summary["pre_pour_source_min"] is None
                else min(summary["pre_pour_source_min"], source)
            )
            for field in _NON_SOURCE_PARTITION_FIELDS:
                summary["pre_pour_non_source_max"][field] = max(
                    summary["pre_pour_non_source_max"][field], counts[field]
                )

    def _sample_substep_containment(self) -> dict[str, Any] | None:
        self._expected_substep_samples += 1
        if self.sample_containment_after_substep is None:
            return None
        value = self.sample_containment_after_substep()
        if value is None:
            return None
        physics_step = self._authority_snapshot()[0]
        self._accumulate_containment(
            value,
            physics_step=physics_step,
            sample_kind="substep",
        )
        if not self.controlled_contact_interlock:
            return None
        counts = {
            field: self._containment_count(value, field)
            for field in _PARTITION_FIELDS
        }
        if counts["source"] == self.expected_particle_count and all(
            counts[field] == 0 for field in _NON_SOURCE_PARTITION_FIELDS
        ):
            return None
        return {
            "kind": "TERMINAL",
            "terminal_kind": "PHYSICAL_PARTICLE_FAILURE",
            "failure_reason": "particle_left_source",
            "physics_step": physics_step,
            "particle_counts": counts,
        }

    @staticmethod
    def _merge_controlled_step_decisions(
        primary: Mapping[str, Any] | None,
        particle: Mapping[str, Any] | None,
    ) -> Mapping[str, Any] | None:
        if particle is None:
            return primary
        if primary is not None and primary.get("kind") == "TERMINAL":
            result = copy.deepcopy(dict(primary))
            result["simultaneous_particle_terminal"] = copy.deepcopy(
                dict(particle)
            )
            return result
        return particle

    def cumulative_containment_summary(self) -> dict[str, Any]:
        summary = copy.deepcopy(self._cumulative_containment)
        summary["substep_sampling_configured"] = (
            self.sample_containment_after_substep is not None
        )
        summary["expected_substep_sample_count"] = self._expected_substep_samples
        summary["substep_sampling_complete"] = bool(
            self.sample_containment_after_substep is not None
            and self._expected_substep_samples > 0
            and summary["substep_sample_count"]
            == self._expected_substep_samples
        )
        return summary

    def seal_attempt(
        self,
        *,
        status: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if self._episode_id is None or self._attempt_id is None:
            raise RuntimeError("episode_not_reset")
        if status not in _ATTEMPT_STATUSES:
            raise ValueError("attempt_status_invalid")
        if reason is not None and (not isinstance(reason, str) or not reason):
            raise ValueError("attempt_reason_invalid")
        if self._attempt_sealed:
            raise RuntimeError("attempt_already_sealed")
        self._attempt_status = status
        self._attempt_sealed = True
        payload = {
            "run_id": self.run_id,
            "attempt_id": self._attempt_id,
            "episode_id": self._episode_id,
            "attempt_status": status,
            "cumulative_containment": self.cumulative_containment_summary(),
        }
        if reason is not None:
            payload["reason"] = reason
        return payload

    def reset_episode(
        self,
        episode_id: str,
        *,
        attempt_id: str | None = None,
    ) -> None:
        if self._pending_controlled_terminal is not None:
            raise RuntimeError("controlled_terminal_pending")
        if (
            self.controlled_contact_interlock
            and self._pending_action is not _NO_PENDING_ACTION
        ):
            raise RuntimeError("controlled_interval_pending")
        if not isinstance(episode_id, str) or not episode_id:
            raise ValueError("episode_id_invalid")
        if attempt_id is not None and (
            not isinstance(attempt_id, str) or not attempt_id
        ):
            raise ValueError("attempt_id_invalid")
        if self._episode_id is not None and not self._attempt_sealed:
            previous_status = "failed" if self._failed else "interrupted"
            previous_reason = (
                "episode_reset_after_runtime_failure"
                if self._failed
                else "episode_reset_before_finalize"
            )
            self._automatically_sealed_attempts.append(
                self.seal_attempt(status=previous_status, reason=previous_reason)
            )

        self._episode_id = episode_id
        self._attempt_id = attempt_id or (
            f"attempt-{next(_PROCESS_ATTEMPT_INDICES):08d}"
        )
        self._attempt_status = "active"
        self._attempt_sealed = False
        self._observation_index = 0
        self._logical_steps = 0
        self._integration_steps = 0
        self._pending_action = _NO_PENDING_ACTION
        self._pending_action_sha256 = None
        self._next_controlled_action_index = 0
        self._pending_controlled_commit = None
        self._pending_controlled_receipt = None
        self._active_precontact_lease = None
        self._required_next_precontact_target_sha256 = None
        self._pending_controlled_terminal = None
        self._pending_controlled_terminal_before = None
        self._pending_controlled_terminal_variant = None
        self._authority_origin = None
        self._last_authority = None
        self._last_state = None
        self._last_score = None
        self._last_source_visual_sync = None
        self._source_visual_sync_all_valid = True
        self._failed = False
        self._render_index = 0
        self._pour_started = False
        self._expected_substep_samples = 0
        self._cumulative_containment = self._empty_containment_summary()

        self._pause_controlled_timeline()
        self.attachment.reset()
        self._surface_runtime.reset_episode(episode_id)
        update_after_substep = getattr(
            self.attachment, "update_after_substep", None
        )
        last_pre_roll_before = self._authority_snapshot()
        try:
            for _ in range(self.reset_pre_roll_substeps):
                last_pre_roll_before = self._authority_snapshot()
                self.attachment.update_before_substep()
                if self.controlled_contact_interlock:
                    self._controlled_world_step()
                else:
                    self.world.step(render=False)
                step_decision = (
                    update_after_substep()
                    if update_after_substep is not None
                    else None
                )
                particle_decision = self._sample_substep_containment()
                decision = self._merge_controlled_step_decisions(
                    step_decision,
                    particle_decision,
                )
                if (
                    self.controlled_contact_interlock
                    and isinstance(decision, Mapping)
                    and decision.get("kind") == "TERMINAL"
                ):
                    if decision.get("terminal_kind") not in (
                        _CONTROLLED_TERMINAL_KINDS
                    ):
                        raise RuntimeError(
                            "controlled_contact_terminal_kind_invalid"
                        )
                    self._pending_controlled_terminal = copy.deepcopy(
                        dict(decision)
                    )
                    self._pending_controlled_terminal_before = (
                        last_pre_roll_before
                    )
                    self._pending_controlled_terminal_variant = "no_action_step"
                    break
            if (
                self.controlled_contact_interlock
                and self._pending_controlled_terminal is None
            ):
                validate_preaction = getattr(
                    self.attachment,
                    "validate_controlled_preaction_authority",
                    None,
                )
                if not callable(validate_preaction):
                    raise RuntimeError(
                        "controlled_preaction_authority_validator_required"
                    )
                decision = validate_preaction()
                if not isinstance(decision, Mapping):
                    raise RuntimeError(
                        "controlled_preaction_authority_decision_required"
                    )
                decision_kind = decision.get("kind")
                if decision_kind == "TERMINAL":
                    if decision.get("terminal_kind") not in (
                        _CONTROLLED_TERMINAL_KINDS
                    ):
                        raise RuntimeError(
                            "controlled_contact_terminal_kind_invalid"
                        )
                    self._pending_controlled_terminal = copy.deepcopy(
                        dict(decision)
                    )
                    self._pending_controlled_terminal_before = (
                        last_pre_roll_before
                    )
                    self._pending_controlled_terminal_variant = "no_action_step"
                elif decision_kind != "CONTINUE":
                    raise RuntimeError(
                        "controlled_preaction_authority_decision_invalid"
                    )
        except Exception:
            self._failed = True
            self._attempt_status = "failed"
            raise
        authority = self._authority_snapshot()
        self._authority_origin = authority
        self._last_authority = authority

    def commit_action(self, action: Any) -> str:
        if self._episode_id is None:
            raise RuntimeError("episode_not_reset")
        if self._attempt_sealed:
            raise RuntimeError("attempt_sealed_requires_reset")
        if self._failed:
            raise RuntimeError("episode_runtime_failed_requires_reset")
        if self._pending_controlled_terminal is not None:
            raise RuntimeError("controlled_terminal_pending")
        if self._observation_index == 0:
            raise RuntimeError("reset_observation_required_before_action")
        if self._pending_action is not _NO_PENDING_ACTION:
            raise RuntimeError("pending_action_already_committed")
        digest = canonical_action_sha256(action)
        self._pending_action = action
        self._pending_action_sha256 = digest
        return digest

    def commit_controlled_action(
        self,
        action: Any,
        proposal: Mapping[str, Any],
    ) -> dict[str, Any]:
        if self._pending_controlled_terminal is not None:
            raise RuntimeError("controlled_terminal_pending")
        if not isinstance(proposal, Mapping):
            raise TypeError("controlled_action_proposal_mapping_required")
        value = copy.deepcopy(dict(proposal))
        proposal_sha256 = value.pop("sha256", None)
        if (
            value.get("authority") != "controlled_action_proposal_v1"
            or proposal_sha256 != canonical_json_sha256(value)
        ):
            raise RuntimeError("controlled_action_proposal_invalid")
        expected_interval = self._observation_index - 1
        action_index = self._next_controlled_action_index
        if (
            expected_interval < 0
            or value.get("interval_index") != expected_interval
            or value.get("control_index") != action_index
            or value.get("action_sha256") != canonical_action_sha256(action)
        ):
            raise RuntimeError("controlled_action_proposal_index_mismatch")
        required_target = self._required_next_precontact_target_sha256
        if required_target is not None and (
            value.get("phase") != "PRECONTACT_SETTLE"
            or value.get("semantic_action_kind") != "ARM_PRECONTACT_SETTLE"
            or value.get("target_token_sha256") != required_target
        ):
            raise RuntimeError("controlled_precontact_next_target_mismatch")
        digest = self.commit_action(action)
        payload = {
            "authority": "controlled_action_commit_v1",
            "proposal_sha256": proposal_sha256,
            "phase": value["phase"],
            "semantic_action_kind": value["semantic_action_kind"],
            "channel": value["channel"],
            "action_sha256": digest,
            "target_token_sha256": value["target_token_sha256"],
            "control_index": value["control_index"],
            "action_index": action_index,
            "interval_index": expected_interval,
            "controller_phase": value["controller_phase"],
            "committed": True,
            "physics_steps_before_commit": 0,
        }
        record = {**payload, "sha256": canonical_json_sha256(payload)}
        self._pending_controlled_commit = record
        self._pending_controlled_receipt = None
        self._next_controlled_action_index += 1
        if required_target is not None:
            self._required_next_precontact_target_sha256 = None
        return copy.deepcopy(record)

    def confirm_controlled_action_applied(
        self,
        receipt: Mapping[str, Any],
    ) -> None:
        if self._pending_controlled_commit is None:
            raise RuntimeError("controlled_action_commit_required")
        if self._pending_controlled_receipt is not None:
            raise RuntimeError("controlled_action_receipt_already_confirmed")
        if not isinstance(receipt, Mapping):
            raise TypeError("controlled_action_receipt_mapping_required")
        value = copy.deepcopy(dict(receipt))
        receipt_sha256 = value.pop("sha256", None)
        commit = self._pending_controlled_commit
        if (
            value.get("authority") != "controlled_action_applied_receipt_v1"
            or receipt_sha256 != canonical_json_sha256(value)
            or value.get("commit_sha256") != commit["sha256"]
            or value.get("proposal_sha256") != commit["proposal_sha256"]
            or value.get("action_sha256") != commit["action_sha256"]
            or value.get("target_token_sha256")
            != commit["target_token_sha256"]
            or value.get("control_index") != commit["control_index"]
            or value.get("action_index") != commit["action_index"]
            or value.get("apply_index") != commit["action_index"]
            or value.get("interval_index") != commit["interval_index"]
            or value.get("controller_phase") != commit["controller_phase"]
            or value.get("applied") is not True
            or value.get("physics_steps_before_receipt") != 0
        ):
            raise RuntimeError("controlled_action_receipt_mismatch")
        self._pending_controlled_receipt = {
            **value,
            "sha256": receipt_sha256,
        }

    def maybe_attach(self, controller: Any, state: Mapping[str, Any]) -> bool:
        if self._episode_id is None:
            raise RuntimeError("episode_not_reset")
        if self._attempt_sealed:
            raise RuntimeError("attempt_sealed_requires_reset")
        if self._failed:
            raise RuntimeError("episode_runtime_failed_requires_reset")
        if self._pending_controlled_terminal is not None:
            raise RuntimeError("controlled_terminal_pending")
        attached = bool(self.attachment.maybe_attach(controller, state))
        if self.controlled_contact_interlock:
            validate_preaction = getattr(
                self.attachment,
                "validate_controlled_preaction_authority",
                None,
            )
            if not callable(validate_preaction):
                raise RuntimeError(
                    "controlled_preaction_authority_validator_required"
                )
            decision = validate_preaction()
            if not isinstance(decision, Mapping):
                raise RuntimeError(
                    "controlled_preaction_authority_decision_required"
                )
            if decision.get("kind") == "TERMINAL":
                if decision.get("terminal_kind") not in (
                    _CONTROLLED_TERMINAL_KINDS
                ):
                    raise RuntimeError("controlled_contact_terminal_kind_invalid")
                self._pending_controlled_terminal = copy.deepcopy(dict(decision))
                self._pending_controlled_terminal_before = (
                    self._authority_snapshot()
                )
                self._pending_controlled_terminal_variant = (
                    "prephysics_transaction"
                )
            elif decision.get("kind") != "CONTINUE":
                raise RuntimeError(
                    "controlled_preaction_authority_decision_invalid"
                )
        return attached

    def queue_controlled_prephysics_failure(
        self,
        *,
        stage: str,
        error: Exception,
        application_outcome: str,
        apply_callback_entered: bool = False,
        apply_callback_normal_return: bool = False,
        proposal: Mapping[str, Any] | None = None,
        commit_record: Mapping[str, Any] | None = None,
        candidate_receipt: Mapping[str, Any] | None = None,
    ) -> None:
        if not self.controlled_contact_interlock:
            raise RuntimeError("controlled_prephysics_failure_requires_interlock")
        if self._episode_id is None or self._observation_index <= 0:
            raise RuntimeError("controlled_prephysics_failure_attempt_inactive")
        if self._attempt_sealed or self._failed:
            raise RuntimeError("controlled_prephysics_failure_attempt_inactive")
        if self._pending_controlled_terminal is not None:
            raise RuntimeError("controlled_terminal_already_pending")
        if stage not in _CONTROLLED_PREPHYSICS_STAGES:
            raise ValueError("controlled_prephysics_failure_stage_invalid")
        if not isinstance(error, Exception):
            raise TypeError("controlled_prephysics_failure_exception_required")
        if application_outcome not in _CONTROLLED_APPLICATION_OUTCOMES:
            raise ValueError("controlled_application_outcome_invalid")
        if type(apply_callback_entered) is not bool or type(
            apply_callback_normal_return
        ) is not bool:
            raise TypeError("controlled_apply_callback_state_bool_required")
        if apply_callback_normal_return and not apply_callback_entered:
            raise ValueError("controlled_apply_callback_state_invalid")

        self._pause_controlled_timeline()
        authority = self._authority_snapshot()
        if self._last_authority is None or authority != self._last_authority:
            raise RuntimeError("controlled_prephysics_failure_world_changed")

        def validated_record(
            record: Mapping[str, Any] | None,
            *,
            authority_name: str,
        ) -> dict[str, Any] | None:
            if record is None:
                return None
            if not isinstance(record, Mapping):
                raise TypeError("controlled_prephysics_record_mapping_required")
            result = copy.deepcopy(dict(record))
            payload = dict(result)
            digest = payload.pop("sha256", None)
            if (
                payload.get("authority") != authority_name
                or digest != canonical_json_sha256(payload)
            ):
                raise ValueError("controlled_prephysics_record_invalid")
            return result

        proposal_value = validated_record(
            proposal,
            authority_name="controlled_action_proposal_v1",
        )
        durable_commit = self._pending_controlled_commit
        if commit_record is not None and (
            durable_commit is None or dict(commit_record) != dict(durable_commit)
        ):
            raise ValueError("controlled_prephysics_commit_not_durable")
        commit_value = validated_record(
            durable_commit,
            authority_name="controlled_action_commit_v1",
        )
        candidate_value = validated_record(
            candidate_receipt,
            authority_name="controlled_action_applied_receipt_v1",
        )
        confirmed_receipt = validated_record(
            self._pending_controlled_receipt,
            authority_name="controlled_action_applied_receipt_v1",
        )
        if confirmed_receipt is not None and candidate_value != confirmed_receipt:
            raise ValueError("controlled_prephysics_receipt_mismatch")
        derived_outcome = _controlled_application_outcome(
            callback_entered=apply_callback_entered,
            callback_normal_return=apply_callback_normal_return,
            candidate_receipt=candidate_value,
            confirmed_receipt=confirmed_receipt,
        )
        if application_outcome != derived_outcome:
            raise ValueError("controlled_application_outcome_mismatch")
        requires_world_termination = bool(
            apply_callback_entered
            or candidate_value is not None
            or confirmed_receipt is not None
        )
        transaction = {
            "authority": "controlled_prephysics_transaction_failure_v1",
            "stage": stage,
            "exception_module": type(error).__module__,
            "exception_type": type(error).__name__,
            "exception_message": str(error),
            "application_outcome": application_outcome,
            "apply_callback_entered": apply_callback_entered,
            "apply_callback_normal_return": apply_callback_normal_return,
            "proposal": proposal_value,
            "commit_record": commit_value,
            "candidate_receipt": candidate_value,
            "confirmed_receipt": confirmed_receipt,
            "physics_step_delta": 0,
            "simulation_time_delta": 0.0,
            "requires_world_termination": requires_world_termination,
        }
        self._pending_controlled_terminal = {
            "kind": "TERMINAL",
            "terminal_kind": "PROTOCOL_FAILURE",
            "failure_reason": f"controlled_prephysics_{stage}_failure",
            "transaction": transaction,
        }
        self._pending_controlled_terminal_before = authority
        self._pending_controlled_terminal_variant = "prephysics_transaction"

        self._pending_action = _NO_PENDING_ACTION
        self._pending_action_sha256 = None
        self._pending_controlled_commit = None
        self._pending_controlled_receipt = None
        self._active_precontact_lease = None
        self._required_next_precontact_target_sha256 = None

    def validate_controlled_action_phase(
        self,
        phase: str,
        *,
        proposal: Mapping[str, Any],
    ) -> bool:
        if self._pending_controlled_terminal is not None:
            raise RuntimeError("controlled_terminal_pending")
        validator = getattr(
            self.attachment,
            "validate_controlled_action_phase",
            None,
        )
        if validator is None:
            return True
        if not callable(validator):
            raise TypeError("controlled_action_phase_validator_invalid")
        decision = validator(phase)
        if not isinstance(decision, Mapping):
            raise TypeError("controlled_action_phase_decision_mapping_required")
        if decision.get("kind") == "CONTINUE":
            return True
        if (
            decision.get("kind") != "TERMINAL"
            or decision.get("terminal_kind") not in _CONTROLLED_TERMINAL_KINDS
        ):
            raise ValueError("controlled_action_phase_decision_invalid")

        self._pause_controlled_timeline()
        authority = self._authority_snapshot()
        if self._last_authority is None or authority != self._last_authority:
            raise RuntimeError("controlled_action_phase_world_changed")
        proposal_value = copy.deepcopy(dict(proposal))
        proposal_payload = dict(proposal_value)
        proposal_digest = proposal_payload.pop("sha256", None)
        if (
            proposal_payload.get("authority") != "controlled_action_proposal_v1"
            or proposal_digest != canonical_json_sha256(proposal_payload)
        ):
            raise ValueError("controlled_action_phase_proposal_invalid")
        transaction = {
            "authority": "controlled_prephysics_transaction_failure_v1",
            "stage": "proposal_validation",
            "exception_module": None,
            "exception_type": None,
            "exception_message": None,
            "application_outcome": "not_invoked",
            "apply_callback_entered": False,
            "apply_callback_normal_return": False,
            "proposal": proposal_value,
            "commit_record": None,
            "candidate_receipt": None,
            "confirmed_receipt": None,
            "physics_step_delta": 0,
            "simulation_time_delta": 0.0,
            "requires_world_termination": False,
        }
        terminal_decision = copy.deepcopy(dict(decision))
        terminal_decision["transaction"] = transaction
        self._pending_controlled_terminal = terminal_decision
        self._pending_controlled_terminal_before = authority
        self._pending_controlled_terminal_variant = "prephysics_transaction"
        self._pending_action = _NO_PENDING_ACTION
        self._pending_action_sha256 = None
        self._pending_controlled_commit = None
        self._pending_controlled_receipt = None
        self._active_precontact_lease = None
        self._required_next_precontact_target_sha256 = None
        return False

    def _verify_authority_delta(
        self,
        before: tuple[int, float],
        after: tuple[int, float],
        *,
        expected_steps: int | None = None,
    ) -> None:
        if expected_steps is None:
            expected_steps = self.physics_substeps_per_observation
        if type(expected_steps) is not int or expected_steps < 0:
            raise ValueError("world_expected_step_delta_invalid")
        actual_steps = after[0] - before[0]
        if actual_steps != expected_steps:
            raise RuntimeError(
                "world_integration_step_delta_invalid:"
                f"expected={expected_steps}:actual={actual_steps}"
            )
        expected_time = expected_steps * self.physics_substep_dt
        actual_time = after[1] - before[1]
        if not math.isclose(actual_time, expected_time, rel_tol=0.0, abs_tol=1.0e-8):
            raise RuntimeError(
                "world_time_delta_invalid:"
                f"expected={expected_time}:actual={actual_time}"
            )

    def _controlled_applied_interval_terminal(
        self,
        *,
        decision: Mapping[str, Any],
        controlled_substeps: Sequence[Mapping[str, Any]],
        continuation_lease: Mapping[str, Any] | None,
        before: tuple[int, float],
        after: tuple[int, float],
        logical_before: int,
        integration_before: int,
    ) -> dict[str, Any]:
        terminal_kind = decision.get("terminal_kind")
        if terminal_kind not in _CONTROLLED_TERMINAL_KINDS:
            raise RuntimeError("controlled_contact_terminal_kind_invalid")
        if not controlled_substeps:
            raise RuntimeError("controlled_contact_terminal_step_missing")
        executed_slots = [
            int(record["substep_slot"]) for record in controlled_substeps
        ]
        expected_executed = list(range(1, len(executed_slots) + 1))
        if executed_slots != expected_executed:
            raise RuntimeError("controlled_contact_terminal_slots_invalid")
        receipt = copy.deepcopy(self._pending_controlled_receipt)
        terminal_step = controlled_substeps[-1]
        payload = {
            "authority": "controlled_terminal_transition_v1",
            "variant": "applied_interval",
            "terminal_kind": terminal_kind,
            "failure_reason": decision.get("failure_reason"),
            "decision": copy.deepcopy(dict(decision)),
            "command_phase": terminal_step["command_phase"],
            "effective_phase": terminal_step["effective_phase"],
            "applied_receipt": receipt,
            "continuation_lease": (
                None
                if continuation_lease is None
                else copy.deepcopy(dict(continuation_lease))
            ),
            "control_index": receipt["control_index"],
            "action_index": receipt["action_index"],
            "apply_index": receipt["apply_index"],
            "interval_index": receipt["interval_index"],
            "executed_substep_slots": executed_slots,
            "omitted_substep_slots": list(
                range(
                    len(executed_slots) + 1,
                    self.physics_substeps_per_observation + 1,
                )
            ),
            "substeps": copy.deepcopy(list(controlled_substeps)),
            "terminal_physics_step": after[0],
            "world_counter_before": {
                "physics_step": before[0],
                "simulation_time": before[1],
            },
            "world_counter_after": {
                "physics_step": after[0],
                "simulation_time": after[1],
            },
            "observation_index": None,
            "frame_index": None,
            "timeline_state_after": "paused",
        }
        terminal = {**payload, "sha256": canonical_json_sha256(payload)}

        self._logical_steps = logical_before
        self._integration_steps = integration_before + len(executed_slots)
        self._last_authority = after
        self._failed = True
        self._attempt_status = "failed"
        self._pending_action = _NO_PENDING_ACTION
        self._pending_action_sha256 = None
        self._pending_controlled_commit = None
        self._pending_controlled_receipt = None
        self._active_precontact_lease = None
        self._required_next_precontact_target_sha256 = None
        return {
            "kind": "CONTROLLED_TERMINAL_TRANSITION",
            "terminal": terminal,
            "attachment": copy.deepcopy(dict(self.attachment.record())),
            "cumulative_containment": self.cumulative_containment_summary(),
        }

    def _controlled_no_action_terminal(self) -> dict[str, Any]:
        decision = self._pending_controlled_terminal
        before = self._pending_controlled_terminal_before
        variant = self._pending_controlled_terminal_variant
        if (
            decision is None
            or before is None
            or variant not in {"no_action_step", "prephysics_transaction"}
        ):
            raise RuntimeError("controlled_no_action_terminal_missing")
        terminal_kind = decision.get("terminal_kind")
        if terminal_kind not in _CONTROLLED_TERMINAL_KINDS:
            raise RuntimeError("controlled_contact_terminal_kind_invalid")
        after = self._authority_snapshot()
        if after != self._last_authority or self.world.is_playing():
            raise RuntimeError("controlled_no_action_terminal_world_changed")
        transaction = decision.get("transaction")
        proposal = None
        commit = None
        candidate_receipt = None
        confirmed_receipt = None
        if isinstance(transaction, Mapping):
            proposal = transaction.get("proposal")
            commit = transaction.get("commit_record")
            candidate_receipt = transaction.get("candidate_receipt")
            confirmed_receipt = transaction.get("confirmed_receipt")
        control_index = None
        interval_index = None
        action_index = None
        apply_index = None
        command_phase = None
        if isinstance(proposal, Mapping):
            control_index = proposal.get("control_index")
            interval_index = proposal.get("interval_index")
            command_phase = proposal.get("phase")
        if isinstance(commit, Mapping):
            control_index = commit.get("control_index")
            action_index = commit.get("action_index")
            interval_index = commit.get("interval_index")
            command_phase = commit.get("phase")
        if isinstance(candidate_receipt, Mapping):
            apply_index = candidate_receipt.get("apply_index")
        if isinstance(confirmed_receipt, Mapping):
            control_index = confirmed_receipt.get("control_index")
            action_index = confirmed_receipt.get("action_index")
            apply_index = confirmed_receipt.get("apply_index")
            interval_index = confirmed_receipt.get("interval_index")
            command_phase = confirmed_receipt.get("phase")
        omitted_slots = (
            list(range(1, self.physics_substeps_per_observation + 1))
            if isinstance(commit, Mapping)
            else []
        )
        payload = {
            "authority": "controlled_terminal_transition_v1",
            "variant": variant,
            "terminal_kind": terminal_kind,
            "failure_reason": decision.get("failure_reason"),
            "decision": copy.deepcopy(decision),
            "command_phase": command_phase,
            "effective_phase": None,
            "applied_receipt": copy.deepcopy(confirmed_receipt),
            "continuation_lease": None,
            "control_index": control_index,
            "action_index": action_index,
            "apply_index": apply_index,
            "interval_index": interval_index,
            "executed_substep_slots": [],
            "omitted_substep_slots": omitted_slots,
            "substeps": [],
            "terminal_physics_step": after[0],
            "world_counter_before": {
                "physics_step": before[0],
                "simulation_time": before[1],
            },
            "world_counter_after": {
                "physics_step": after[0],
                "simulation_time": after[1],
            },
            "observation_index": None,
            "frame_index": None,
            "timeline_state_after": "paused",
        }
        terminal = {**payload, "sha256": canonical_json_sha256(payload)}
        self._pending_controlled_terminal = None
        self._pending_controlled_terminal_before = None
        self._pending_controlled_terminal_variant = None
        self._failed = True
        self._attempt_status = "failed"
        return {
            "kind": "CONTROLLED_TERMINAL_TRANSITION",
            "terminal": terminal,
            "attachment": copy.deepcopy(dict(self.attachment.record())),
            "cumulative_containment": self.cumulative_containment_summary(),
        }

    def _render_surface(self, token: SurfaceFrameToken) -> dict[str, Any]:
        before = self._authority_snapshot()
        warmup_updates = (
            self.initial_render_warmup_updates
            if token.observation_index == 0
            else 0
        )
        warmup_start = time.perf_counter()
        for _ in range(warmup_updates):
            self.world.render()
            if self._authority_snapshot() != before:
                raise RuntimeError("render_advanced_physics_or_timeline")
        warmup_seconds = time.perf_counter() - warmup_start
        self.world.render()
        after = self._authority_snapshot()
        raw_step_delta = after[0] - before[0]
        self._render_index += 1
        render_token = hashlib.sha256(
            f"{token.identity}:{self._render_index}".encode("ascii")
        ).hexdigest()
        return {
            "render_token": render_token,
            "surface_token": token.identity,
            "logical_steps_before": token.logical_step_after,
            "logical_steps_after": token.logical_step_after + raw_step_delta,
            "integration_steps_before": token.integration_step_after,
            "integration_steps_after": token.integration_step_after + raw_step_delta,
            "timeline_time_before": token.simulation_time_after,
            "timeline_time_after": token.simulation_time_after + (after[1] - before[1]),
            "initial_warmup_updates": warmup_updates,
            "initial_warmup_seconds": warmup_seconds,
            "render_call_count": warmup_updates + 1,
        }

    def _capture_model_cameras(
        self,
        token: SurfaceFrameToken,
        render_record: Mapping[str, Any],
    ) -> Mapping[str, np.ndarray]:
        del token, render_record
        state = self.task.step()
        if not isinstance(state, Mapping):
            raise ValueError("task_state_mapping_required")
        if self.adapt_state is not None:
            state = self.adapt_state(state)
            if not isinstance(state, Mapping):
                raise ValueError("adapted_task_state_mapping_required")
        camera_data = state.get("camera_data")
        if not isinstance(camera_data, Mapping):
            raise ValueError("model_camera_data_mapping_required")
        if set(camera_data) != set(self.expected_camera_keys):
            raise ValueError(
                "model_camera_keys_mismatch:"
                f"expected={sorted(self.expected_camera_keys)}:"
                f"actual={sorted(str(key) for key in camera_data)}"
            )
        for name in self.expected_camera_keys:
            array = np.asarray(camera_data[name])
            if array.shape != self.expected_camera_shape:
                raise ValueError(
                    f"model_camera_shape_mismatch:{name}:"
                    f"expected={self.expected_camera_shape}:actual={array.shape}"
                )
            if array.dtype != np.uint8:
                raise ValueError(
                    f"model_camera_dtype_mismatch:{name}:actual={array.dtype}"
                )
        self._last_state = state
        return {name: camera_data[name] for name in self.expected_camera_keys}

    @staticmethod
    def _model_state_pose_record(state: Mapping[str, Any]) -> dict[str, Any] | None:
        if "object_position" not in state or "object_quaternion" not in state:
            return None
        position = np.asarray(state["object_position"], dtype=np.float64)
        quaternion = np.asarray(state["object_quaternion"], dtype=np.float64)
        if position.shape != (3,) or not np.isfinite(position).all():
            raise ValueError("model_state_object_position_invalid")
        if quaternion.shape != (4,) or not np.isfinite(quaternion).all():
            raise ValueError("model_state_object_quaternion_invalid")
        return {
            "object_position": position.tolist(),
            "object_quaternion_xyzw": quaternion.tolist(),
        }

    def _validate_score(self, value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise ValueError("fluid_score_mapping_required")
        score = dict(value)
        if int(score.get("particle_count", -1)) != self.expected_particle_count:
            raise ValueError("fluid_score_particle_count_mismatch")
        if score.get("partition_complete") is not True or score.get("valid") is not True:
            raise ValueError("fluid_score_invalid")
        if type(score.get("fluid_transfer_passed")) is not bool:
            raise ValueError("fluid_transfer_passed_missing")
        for field in (
            "strict_zero_spill_transfer_passed",
            "task_transfer_passed",
            "expert_transfer_passed",
        ):
            if type(score.get(field)) is not bool:
                raise ValueError(f"{field}_missing")
        target_fraction = score.get("target_fraction")
        if (
            isinstance(target_fraction, bool)
            or not isinstance(target_fraction, (int, float, np.number))
            or not math.isfinite(float(target_fraction))
            or not 0.0 <= float(target_fraction) <= 1.0
        ):
            raise ValueError("target_fraction_invalid")
        if (
            score["fluid_transfer_passed"]
            != score["strict_zero_spill_transfer_passed"]
        ):
            raise ValueError("strict_transfer_compatibility_alias_mismatch")
        return score

    def _sync_source_visual_state(self) -> dict[str, Any] | None:
        if self.sync_source_visual_state is None:
            return None
        value = self.sync_source_visual_state()
        if not isinstance(value, Mapping):
            raise ValueError("source_visual_sync_mapping_required")
        result = dict(value)
        if type(result.get("valid")) is not bool:
            raise ValueError("source_visual_sync_valid_bool_required")
        return result

    def observe(self) -> dict[str, Any]:
        if self._episode_id is None:
            raise RuntimeError("episode_not_reset")
        if self._attempt_sealed:
            raise RuntimeError("attempt_sealed_requires_reset")
        if self._pending_controlled_terminal is not None:
            return self._controlled_no_action_terminal()
        if self._failed:
            raise RuntimeError("episode_runtime_failed_requires_reset")
        observe_start = time.perf_counter()
        is_reset = self._observation_index == 0
        controlled_interlock_record = None
        if is_reset:
            if self._pending_action is not _NO_PENDING_ACTION:
                raise RuntimeError("reset_observation_must_not_have_action")
            before = self._authority_snapshot()
            if before != self._last_authority:
                raise RuntimeError("reset_observation_authority_changed")
            after = before
            action_hash = None
            caused_by_action_index = None
            logical_before = self._logical_steps
            integration_before = self._integration_steps
        else:
            if self._pending_action is _NO_PENDING_ACTION:
                raise RuntimeError("pending_action_required")
            if (
                self._pending_controlled_commit is not None
                and self._pending_controlled_receipt is None
            ):
                raise RuntimeError("controlled_action_receipt_required")
            if (
                self.controlled_contact_interlock
                and self._pending_controlled_receipt is None
            ):
                raise RuntimeError("controlled_action_receipt_required")
            before = self._authority_snapshot()
            if before != self._last_authority:
                raise RuntimeError("world_authority_changed_outside_fluid_loop")
            logical_before = self._logical_steps
            integration_before = self._integration_steps
            controlled_substeps = []
            precontact_latched = False
            continuation_lease = None
            terminal_decision = None
            try:
                for slot in range(1, self.physics_substeps_per_observation + 1):
                    command_phase = (
                        self._pending_controlled_receipt["phase"]
                        if self.controlled_contact_interlock
                        else None
                    )
                    effective_phase = (
                        "PRECONTACT_SETTLE"
                        if self._active_precontact_lease is not None
                        else command_phase
                    )
                    set_effective_phase = getattr(
                        self.attachment,
                        "set_controlled_effective_phase",
                        None,
                    )
                    if self.controlled_contact_interlock:
                        if not callable(set_effective_phase):
                            raise RuntimeError(
                                "controlled_effective_phase_setter_required"
                            )
                        set_effective_phase(effective_phase)
                    self.attachment.update_before_substep()
                    if self.controlled_contact_interlock:
                        self._controlled_world_step()
                    else:
                        self.world.step(render=False)
                    update_after_substep = getattr(
                        self.attachment, "update_after_substep", None
                    )
                    decision = (
                        update_after_substep()
                        if update_after_substep is not None
                        else None
                    )
                    particle_decision = self._sample_substep_containment()
                    decision = self._merge_controlled_step_decisions(
                        decision,
                        particle_decision,
                    )
                    if self.controlled_contact_interlock:
                        if not isinstance(decision, Mapping):
                            raise RuntimeError(
                                "controlled_contact_step_decision_required"
                            )
                        decision_kind = decision.get("kind")
                        deadline_grace = decision.get(
                            "phase_deadline_exit_grace"
                        )
                        if deadline_grace is not None:
                            if (
                                not isinstance(deadline_grace, Mapping)
                                or deadline_grace.get("phase")
                                not in {"PREGRASP", "ALIGN", "INSERT"}
                            ):
                                raise RuntimeError(
                                    "controlled_phase_deadline_grace_invalid"
                                )
                            if slot != self.physics_substeps_per_observation:
                                phase = deadline_grace["phase"]
                                decision = {
                                    "kind": "TERMINAL",
                                    "terminal_kind": "PHYSICAL_TIMEOUT",
                                    "failure_reason": (
                                        f"{phase}_timeout_unaligned_exit"
                                    ),
                                    "phase_deadline_exit_grace": copy.deepcopy(
                                        dict(deadline_grace)
                                    ),
                                }
                                decision_kind = "TERMINAL"
                        if decision_kind == "INTENDED_PRECONTACT":
                            if self._active_precontact_lease is None:
                                evidence = decision.get("evidence")
                                if not isinstance(evidence, Mapping):
                                    raise RuntimeError(
                                        "controlled_contact_latch_evidence_required"
                                    )
                                evidence = copy.deepcopy(dict(evidence))
                                if (
                                    evidence.get("physics_step")
                                    != self._authority_snapshot()[0]
                                ):
                                    raise RuntimeError(
                                        "controlled_contact_latch_step_mismatch"
                                    )
                                lease = build_precontact_continuation_lease(
                                    applied_receipt=(
                                        self._pending_controlled_receipt
                                    ),
                                    contact_physics_index=evidence["physics_step"],
                                    contact_substep_slot=slot,
                                    substeps_per_interval=(
                                        self.physics_substeps_per_observation
                                    ),
                                    contact_evidence_sha256=evidence.get(
                                        "evidence_sha256"
                                    ),
                                )
                                evidence["applied_receipt"] = copy.deepcopy(
                                    self._pending_controlled_receipt
                                )
                                latch = getattr(
                                    self.attachment,
                                    "latch_intended_precontact",
                                    None,
                                )
                                if not callable(latch) or latch(evidence) is not True:
                                    raise RuntimeError(
                                        "controlled_contact_controller_latch_failed"
                                    )
                                self._active_precontact_lease = lease
                                self._required_next_precontact_target_sha256 = (
                                    lease["target_token_sha256"]
                                )
                                continuation_lease = copy.deepcopy(lease)
                                precontact_latched = True
                        elif decision_kind == "TERMINAL":
                            terminal_kind = decision.get("terminal_kind")
                            if terminal_kind not in _CONTROLLED_TERMINAL_KINDS:
                                raise RuntimeError(
                                    "controlled_contact_terminal_kind_invalid"
                                )
                            terminal_decision = copy.deepcopy(dict(decision))
                        elif decision_kind != "CONTINUE":
                            raise RuntimeError(
                                "controlled_contact_step_decision_invalid"
                            )
                        controlled_substeps.append(
                            {
                                "substep_slot": slot,
                                "physics_step": self._authority_snapshot()[0],
                                "command_phase": command_phase,
                                "controller_phase": (
                                    self._pending_controlled_receipt[
                                        "controller_phase"
                                    ]
                                ),
                                "effective_phase": effective_phase,
                                "decision": decision_kind,
                                "phase_deadline_exit_grace": copy.deepcopy(
                                    decision.get("phase_deadline_exit_grace")
                                ),
                            }
                        )
                        if terminal_decision is not None:
                            break
            except Exception:
                self._failed = True
                self._attempt_status = "failed"
                raise
            try:
                after = self._authority_snapshot()
                self._verify_authority_delta(
                    before,
                    after,
                    expected_steps=(
                        len(controlled_substeps)
                        if terminal_decision is not None
                        else None
                    ),
                )
            except Exception:
                self._failed = True
                self._attempt_status = "failed"
                raise
            if terminal_decision is not None:
                return self._controlled_applied_interval_terminal(
                    decision=terminal_decision,
                    controlled_substeps=controlled_substeps,
                    continuation_lease=continuation_lease,
                    before=before,
                    after=after,
                    logical_before=logical_before,
                    integration_before=integration_before,
                )
            action_hash = self._pending_action_sha256
            caused_by_action_index = self._observation_index - 1
            if self.controlled_contact_interlock:
                controlled_interlock_record = {
                    "authority": "controlled_contact_substep_interlock_v1",
                    "precontact_latched": precontact_latched,
                    "continuation_lease": continuation_lease,
                    "substeps": controlled_substeps,
                    "timeline_state_after": "paused",
                }
                self._active_precontact_lease = None

        logical_after = logical_before + (0 if is_reset else 1)
        integration_after = integration_before + (
            0 if is_reset else self.physics_substeps_per_observation
        )
        transition = ObservationTransition(
            episode_id=self._episode_id,
            observation_index=self._observation_index,
            caused_by_action_index=caused_by_action_index,
            logical_step_before=logical_before,
            logical_step_after=logical_after,
            integration_step_before=integration_before,
            integration_step_after=integration_after,
            simulation_time_before=integration_before * self.physics_substep_dt,
            simulation_time_after=integration_after * self.physics_substep_dt,
            action_sha256=action_hash,
        )

        try:
            source_visual_sync = self._sync_source_visual_state()
            self._last_source_visual_sync = source_visual_sync
            if source_visual_sync is not None:
                self._source_visual_sync_all_valid = (
                    self._source_visual_sync_all_valid
                    and source_visual_sync["valid"]
                )
            positions = validate_simulation_points(
                self.read_particles(),
                expected_particle_count=self.expected_particle_count,
            )
            score = self._validate_score(self.score_particles(positions))
            self._accumulate_containment(
                score,
                physics_step=after[0],
                sample_kind="observation",
            )
            self._last_state = None
            record = self._surface_runtime.process_observation(transition, positions)
            if self._last_state is None:
                raise RuntimeError("model_state_not_captured")
            model_state_pose = self._model_state_pose_record(self._last_state)
            if model_state_pose is not None:
                record["model_state_pose"] = model_state_pose
            if source_visual_sync is not None:
                record["source_visual_sync"] = source_visual_sync
            record["camera_contract"] = dict(self.camera_contract_identity)
            record["reset_pre_roll_substeps"] = self.reset_pre_roll_substeps
            record["run_id"] = self.run_id
            record["attempt_id"] = self._attempt_id
            record["sample_index"] = next(_PROCESS_SAMPLE_INDICES)
            record["attempt_status"] = self._attempt_status
            record["cumulative_containment"] = (
                self.cumulative_containment_summary()
            )
            if controlled_interlock_record is not None:
                record["controlled_contact_interlock"] = (
                    controlled_interlock_record
                )
            record["latency_seconds"]["model_ready_total"] = (
                time.perf_counter() - observe_start
            )
        except Exception:
            self._failed = True
            self._attempt_status = "failed"
            raise

        self._logical_steps = logical_after
        self._integration_steps = integration_after
        self._last_authority = after
        self._last_score = score
        self._observation_index += 1
        self._pending_action = _NO_PENDING_ACTION
        self._pending_action_sha256 = None
        self._pending_controlled_commit = None
        self._pending_controlled_receipt = None
        return {
            "state": self._last_state,
            "record": record,
            "score": score,
            "attachment": dict(self.attachment.record()),
        }

    def finalize_episode(
        self,
        *,
        controller_completed: bool,
        acceptance_mode: str = "production_pour_v1",
        controller_evidence: Mapping[str, Any] | None = None,
        terminal_phase: str | None = None,
        terminal_action: Any = _TERMINAL_ACTION_UNSET,
    ) -> dict[str, Any]:
        if type(controller_completed) is not bool:
            raise TypeError("controller_completed_bool_required")
        if acceptance_mode not in (
            "production_pour_v1",
            "contact_acquisition_probe_v1",
            "close_contact_allowed_v1",
        ):
            raise ValueError("fluid_acceptance_mode_unsupported")
        if self._attempt_sealed:
            raise RuntimeError("attempt_already_sealed")
        if self._last_score is None:
            raise RuntimeError("fluid_observation_required_before_finalize")
        strict_passed = bool(
            self._last_score["strict_zero_spill_transfer_passed"]
        )
        task_passed = bool(self._last_score["task_transfer_passed"])
        terminal_expert_passed = bool(
            self._last_score["expert_transfer_passed"]
        )
        final_target_particles = self._containment_count(
            self._last_score, "target"
        )
        minimum_expert_target_particles = (
            9 * self.expected_particle_count + 9
        ) // 10
        summary = self.cumulative_containment_summary()
        pre_pour_containment_valid = bool(
            summary["pre_pour_source_min"] == self.expected_particle_count
            and all(
                count == 0
                for count in summary["pre_pour_non_source_max"].values()
            )
        )
        cumulative_containment_valid = bool(
            summary["substep_sampling_complete"]
            and summary["partition_integrity_valid"]
            and summary["below_table_max"] == 0
            and summary["nonfinite_max"] == 0
            and pre_pour_containment_valid
        )
        terminal_expert_requirements_valid = bool(
            terminal_expert_passed
            and final_target_particles >= minimum_expert_target_particles
        )
        attachment_record = self.attachment.record()
        expected_dynamic_grasp = (
            self.expected_source_ownership == "contact_friction_dynamic_v1"
        )
        dynamic_grasp = bool(
            expected_dynamic_grasp or "expert_grasp_valid" in attachment_record
        )
        dynamic_grasp_contract_valid = None
        if expected_dynamic_grasp:
            dynamic_grasp_contract_valid = bool(
                attachment_record.get("mode")
                == "contact_friction_dynamic_v1"
                and attachment_record.get("source_dynamic") is True
                and attachment_record.get("mechanical_attachment_used") is False
                and type(
                    attachment_record.get("source_pose_write_count_after_play")
                )
                is int
                and attachment_record["source_pose_write_count_after_play"] == 0
                and type(
                    attachment_record.get("kinematic_target_update_count")
                )
                is int
                and attachment_record["kinematic_target_update_count"] == 0
                and attachment_record.get("qualified") is True
                and attachment_record.get("expert_grasp_valid") is True
                and attachment_record.get("failure_reason") is None
            )
            expert_attachment_valid = dynamic_grasp_contract_valid
        else:
            expert_attachment_valid = attachment_record.get(
                "expert_grasp_valid" if dynamic_grasp else "expert_attachment_valid",
                True,
            )
        if type(expert_attachment_valid) is not bool:
            raise ValueError("expert_attachment_valid_bool_required")
        source_visual_sync_valid = (
            True
            if self.sync_source_visual_state is None
            else self._last_source_visual_sync is not None
            and self._source_visual_sync_all_valid
        )
        probe_control_contract = None
        if acceptance_mode in {
            "contact_acquisition_probe_v1",
            "close_contact_allowed_v1",
        }:
            probe_control_contract = contact_acquisition_probe_control_contract(
                controller_evidence=controller_evidence,
                attachment_evidence=attachment_record,
                expected_source_ownership=self.expected_source_ownership,
                controller_completed=controller_completed,
                terminal_phase=terminal_phase,
                terminal_action=terminal_action,
                pour_started=self._pour_started,
                cumulative_containment_valid=cumulative_containment_valid,
                source_visual_sync_valid=source_visual_sync_valid,
            )
        attempt_status = (
            "failed" if self._failed or not controller_completed else "completed"
        )
        seal = self.seal_attempt(status=attempt_status)
        contact_acquisition_probe_accepted = bool(
            acceptance_mode
            in {
                "contact_acquisition_probe_v1",
                "close_contact_allowed_v1",
            }
            and probe_control_contract is not None
            and probe_control_contract["valid"]
        )
        expert_episode_accepted = bool(
            acceptance_mode == "production_pour_v1"
            and controller_completed
            and terminal_expert_requirements_valid
            and cumulative_containment_valid
            and expert_attachment_valid
            and source_visual_sync_valid
        )
        success = (
            contact_acquisition_probe_accepted
            if acceptance_mode == "contact_acquisition_probe_v1"
            else controller_completed and task_passed
        )
        result = {
            **seal,
            "acceptance_mode": acceptance_mode,
            "controller_completed": controller_completed,
            "fluid_transfer_passed": strict_passed,
            "strict_zero_spill_transfer_passed": strict_passed,
            "task_transfer_passed": task_passed,
            "expert_transfer_passed": terminal_expert_passed,
            "terminal_expert_transfer_passed": terminal_expert_passed,
            "terminal_expert_requirements_valid": (
                terminal_expert_requirements_valid
            ),
            "minimum_expert_target_particles": (
                minimum_expert_target_particles
            ),
            "final_target_particles": final_target_particles,
            "pre_pour_containment_valid": pre_pour_containment_valid,
            "cumulative_containment_valid": cumulative_containment_valid,
            "expert_attachment_valid": expert_attachment_valid,
            "dynamic_grasp_contract_valid": dynamic_grasp_contract_valid,
            "source_visual_sync_valid": source_visual_sync_valid,
            "contact_acquisition_probe_accepted": (
                contact_acquisition_probe_accepted
            ),
            "expert_episode_accepted": expert_episode_accepted,
            "success": success,
        }
        if dynamic_grasp:
            result["expert_grasp_valid"] = expert_attachment_valid
        if probe_control_contract is not None:
            result["probe_control_contract"] = probe_control_contract
        return result
